import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func

from app.core.db import get_db
from app.core.masking import mask
from app.core.security import require, READ, WORK
from app.models import Alert, Account, Customer, Transaction, FeatureSnapshot
from app.modules.audit.service import audit
from app.modules.graph.signals import ego_graph_payload

router = APIRouter(prefix="/alerts", tags=["alerts"])


def alert_out(db, a):
    acct = db.get(Account, a.account_id)
    return {"id": str(a.id), "alert_ref": a.alert_ref, "account_ref": acct.account_ref,
            "scenario_key": a.scenario_key, "severity": a.severity, "score": a.score, "status": a.status,
            "assigned_to": str(a.assigned_to) if a.assigned_to else None,
            "created_at": a.created_at.isoformat()}


@router.get("")
def list_alerts(status: str | None = None, severity: str | None = None, scenario: str | None = None,
                min_score: float | None = None, since: datetime | None = None,
                page: int = 1, page_size: int = 25,
                db=Depends(get_db), user=Depends(require(*READ))):
    page_size = min(page_size, 100)
    q = select(Alert)
    if status:
        q = q.where(Alert.status == status)
    if severity:
        q = q.where(Alert.severity == severity)
    if scenario:
        q = q.where(Alert.scenario_key == scenario)
    if min_score is not None:
        q = q.where(Alert.score >= min_score)
    if since:
        q = q.where(Alert.created_at >= since)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Alert.score.desc(), Alert.created_at.desc())
                      .limit(page_size).offset((page - 1) * page_size)).all()
    items = [alert_out(db, a) for a in rows]
    if user.role == "auditor":
        for it in items:
            it["account_ref"] = mask(it["account_ref"])
    return {"total": total, "page": page, "items": items}


@router.get("/{alert_id}")
def alert_detail(alert_id: uuid.UUID, db=Depends(get_db), _=Depends(require(*READ))):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404)
    ids = [uuid.UUID(i) for i in a.reasons_json.get("linked_transaction_ids", [])]
    txs = db.scalars(select(Transaction).where(Transaction.id.in_(ids)).order_by(Transaction.occurred_at)).all()
    refs = {x.id: x.account_ref for x in db.scalars(select(Account))}
    cust = db.scalar(select(Customer).join(Account, Account.customer_id == Customer.id)
                     .where(Account.id == a.account_id))
    out30 = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.source_account_id == a.account_id,
        Transaction.occurred_at > a.created_at - timedelta(days=30))) or Decimal(0)
    snap = db.get(FeatureSnapshot, a.feature_snapshot_id) if a.feature_snapshot_id else None
    return {**alert_out(db, a), "reasons": a.reasons_json,
            "transactions": [{"id": str(t.id), "event_id": t.event_id, "from": refs[t.source_account_id],
                              "to": refs[t.destination_account_id], "amount": str(t.amount),
                              "occurred_at": t.occurred_at.isoformat()} for t in txs],
            "baseline": {"customer_id": str(cust.id), "expected_monthly_max": str(cust.expected_monthly_max),
                         "observed_outgoing_30d": str(out30), "risk_rating": cust.risk_rating,
                         "kyc_status": cust.kyc_status},
            "feature_snapshot": snap.feature_json if snap else None}


class Assign(BaseModel):
    assignee_id: uuid.UUID


@router.post("/{alert_id}/assign")
def assign(alert_id: uuid.UUID, b: Assign, db=Depends(get_db), user=Depends(require(*WORK))):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404)
    before = {"assigned_to": str(a.assigned_to) if a.assigned_to else None, "status": a.status}
    a.assigned_to = b.assignee_id
    if a.status == "open":
        a.status = "in_review"
    audit(db, user, "alert.assign", "alert", a.id, before,
          {"assigned_to": str(b.assignee_id), "status": a.status})
    db.commit()
    return alert_out(db, a)


@router.get("/{alert_id}/graph")
def alert_graph(alert_id: uuid.UUID, db=Depends(get_db), _=Depends(require(*READ))):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404)
    return ego_graph_payload(db, a.account_id, a.created_at)