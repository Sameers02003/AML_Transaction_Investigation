import uuid
import numpy as np
from app.modules.scoring.anomaly import anomaly_scorer
from app.modules.scoring.features import compute_features
from datetime import timedelta, datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from app.core.db import get_db
from app.core.security import require, READ
from app.models import *
from app.modules.audit.service import audit
from app.modules.rules.engine import RULES

router = APIRouter(tags=["misc"])

@router.get("/transactions/{tx_id}")
def tx_detail(tx_id: uuid.UUID, db=Depends(get_db), _=Depends(require(*READ))):
    t = db.get(Transaction, tx_id)
    if not t: raise HTTPException(404)
    alerts = db.scalars(select(Alert).where(Alert.transaction_id == t.id)).all()
    return {"id": str(t.id), "event_id": t.event_id, "amount": str(t.amount), "currency": t.currency, "channel": t.channel,
            "occurred_at": t.occurred_at.isoformat(), "status": t.status,
            "alerts": [{"id": str(a.id), "scenario_key": a.scenario_key, "score": a.score} for a in alerts]}

@router.get("/customers/{customer_id}/risk-summary")
def risk_summary(customer_id: uuid.UUID, db=Depends(get_db), _=Depends(require(*READ))):
    c = db.get(Customer, customer_id)
    if not c: raise HTTPException(404)
    accts = db.scalars(select(Account).where(Account.customer_id == c.id)).all()
    ids = [a.id for a in accts]
    since = datetime.now(timezone.utc) - timedelta(days=30)
    out30 = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.source_account_id.in_(ids), Transaction.occurred_at > since))
    in30 = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.destination_account_id.in_(ids), Transaction.occurred_at > since))
    alerts = db.scalars(select(Alert).where(Alert.account_id.in_(ids)).order_by(Alert.created_at.desc()).limit(20)).all()
    return {"customer_ref": c.customer_ref, "type": c.customer_type, "occupation": c.occupation_or_business,
            "risk_rating": c.risk_rating, "kyc_status": c.kyc_status, "expected_monthly_max": str(c.expected_monthly_max),
            "accounts": [{"account_ref": a.account_ref, "opened_at": a.opened_at.isoformat(), "status": a.status} for a in accts],
            "last_30d": {"incoming": str(in30), "outgoing": str(out30)},
            "prior_alerts": [{"id": str(a.id), "alert_ref": a.alert_ref, "scenario_key": a.scenario_key, "status": a.status} for a in alerts]}

@router.get("/metrics/aml")
def aml_metrics(db=Depends(get_db), _=Depends(require(*READ))):
    tx_total = db.scalar(select(func.count(Transaction.id))) or 0
    alerts_total = db.scalar(select(func.count(Alert.id))) or 0
    by_sev = dict(db.execute(select(Alert.severity, func.count()).group_by(Alert.severity)).all())
    in_case = db.scalar(select(func.count(func.distinct(CaseAlert.alert_id)))) or 0
    open_cases = db.scalars(select(Case).where(Case.status.notin_(["closed", "escalated"]))).all()
    now = datetime.now(timezone.utc)
    disp = dict(db.execute(select(Case.disposition, func.count()).where(Case.disposition.isnot(None)).group_by(Case.disposition)).all())
    return {"transactions": tx_total, "alerts": alerts_total, "alerts_per_10k_tx": round(alerts_total / tx_total * 10000, 2) if tx_total else 0,
            "alerts_by_severity": by_sev, "alert_to_case_rate": round(in_case / alerts_total, 3) if alerts_total else 0,
            "open_cases": len(open_cases),
            "oldest_open_case_hours": round(max(((now - c.opened_at).total_seconds() / 3600 for c in open_cases), default=0), 1),
            "dispositions": disp}

@router.get("/rules")
def list_rules(db=Depends(get_db), _=Depends(require(*READ))):
    return [{"id": str(r.id), "rule_key": r.rule_key, "version": r.version, "enabled": r.enabled, "parameters": r.parameters_json,
             "effective_from": r.effective_from.isoformat(), "approved_by": r.approved_by}
            for r in db.scalars(select(RuleDefinition).order_by(RuleDefinition.rule_key, RuleDefinition.version.desc()))]

class RuleNewVersion(BaseModel):
    parameters: dict
    enabled: bool = True

@router.post("/rules/{rule_key}/versions", status_code=201)
def new_rule_version(rule_key: str, b: RuleNewVersion, db=Depends(get_db), user=Depends(require("administrator", "compliance_officer"))):
    if rule_key not in RULES: raise HTTPException(404)
    last = db.scalar(select(func.max(RuleDefinition.version)).where(RuleDefinition.rule_key == rule_key)) or 0
    r = RuleDefinition(rule_key=rule_key, version=last + 1, enabled=b.enabled, parameters_json=b.parameters,
                       effective_from=datetime.now(timezone.utc), approved_by=user.username)
    db.add(r); db.flush()
    audit(db, user, "rule.new_version", "rule", rule_key, None, {"version": r.version, "parameters": b.parameters})
    db.commit()
    return {"rule_key": rule_key, "version": r.version}

def psi(expected, actual, eps=1e-4):
    e = np.array(expected, float) / max(sum(expected), 1) + eps
    a = np.array(actual, float) / max(sum(actual), 1) + eps
    return float(np.sum((a - e) * np.log(a / e)))


@router.get("/metrics/model")
def model_metrics(db=Depends(get_db), _=Depends(require(*READ))):
    b = anomaly_scorer.b
    if not b:
        return {"model": None}
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    sample = db.execute(select(Transaction.source_account_id, Transaction.occurred_at)
                        .where(Transaction.occurred_at > since).limit(300)).all()
    raws = []
    for acct, t in sample:
        f = compute_features(db, acct, t)
        x = np.array([[f[n] for n in b["feature_names"]]])
        raws.append(float(-b["pipeline"].score_samples(x)[0]))
    lo, hi = b["hist_range"]
    live_hist = np.histogram(np.clip(raws, lo, hi), bins=10, range=(lo, hi))[0].tolist() if raws else [0] * 10
    return {"model": {"version": b["version"], "trained_until": b["trained_until"], "n_train": b["n_train"]},
            "train_hist": b["train_hist"], "live_hist": live_hist,
            "psi": round(psi(b["train_hist"], live_hist), 4) if raws else None,
            "note": "PSI above 0.2 usually warrants investigation before the model is trusted or replaced."}