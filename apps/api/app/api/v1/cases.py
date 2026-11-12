import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import require, READ, WORK
from app.models import Case, CaseAlert, CaseNote, EvidenceItem, Alert, AuditEvent
from app.modules.audit.service import audit

router = APIRouter(prefix="/cases", tags=["cases"])
DISPOSITIONS = {"false_positive", "explainable_activity", "escalate", "further_review"}
SENIOR = ("senior_investigator", "compliance_officer")

def case_out(c): return {"id": str(c.id), "case_ref": c.case_ref, "priority": c.priority, "owner_id": str(c.owner_id),
                         "status": c.status, "opened_at": c.opened_at.isoformat(), "disposition": c.disposition,
                         "closed_at": c.closed_at.isoformat() if c.closed_at else None}

class CaseCreate(BaseModel):
    alert_ids: list[uuid.UUID] = Field(min_length=1)
    priority: str = "medium"

@router.post("", status_code=201)
def create_case(b: CaseCreate, db=Depends(get_db), user=Depends(require(*WORK))):
    alerts = db.scalars(select(Alert).where(Alert.id.in_(b.alert_ids))).all()
    if len(alerts) != len(set(b.alert_ids)): raise HTTPException(404, "alert not found")
    c = Case(case_ref="CASE-" + uuid.uuid4().hex[:8].upper(), priority=b.priority, owner_id=user.id, status="open")
    db.add(c); db.flush()
    for a in alerts:
        db.add(CaseAlert(case_id=c.id, alert_id=a.id)); a.status = "in_case"
    audit(db, user, "case.create", "case", c.id, None, {"alert_ids": [str(i) for i in b.alert_ids]})
    db.commit()
    return case_out(c)

@router.get("")
def list_cases(status: str | None = None, db=Depends(get_db), _=Depends(require(*READ))):
    q = select(Case).order_by(Case.opened_at.desc())
    if status: q = q.where(Case.status == status)
    return [case_out(c) for c in db.scalars(q)]

@router.get("/{case_id}")
def get_case(case_id: uuid.UUID, db=Depends(get_db), _=Depends(require(*READ))):
    c = db.get(Case, case_id)
    if not c: raise HTTPException(404)
    alert_ids = [r.alert_id for r in db.scalars(select(CaseAlert).where(CaseAlert.case_id == c.id))]
    alerts = db.scalars(select(Alert).where(Alert.id.in_(alert_ids))).all()
    notes = db.scalars(select(CaseNote).where(CaseNote.case_id == c.id).order_by(CaseNote.created_at)).all()
    ev = db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == c.id)).all()
    timeline = db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "case", AuditEvent.entity_id == str(c.id))
                          .order_by(AuditEvent.occurred_at)).all()
    return {**case_out(c),
            "alerts": [{"id": str(a.id), "alert_ref": a.alert_ref, "scenario_key": a.scenario_key, "score": a.score} for a in alerts],
            "notes": [{"id": str(n.id), "author_id": str(n.author_id), "note": n.note, "created_at": n.created_at.isoformat()} for n in notes],
            "evidence": [{"type": e.evidence_type, "reference": e.reference, "hash": e.hash} for e in ev],
            "timeline": [{"action": t.action, "actor_id": str(t.actor_id) if t.actor_id else None,
                          "at": t.occurred_at.isoformat(), "after": t.after_json} for t in timeline]}

class NoteIn(BaseModel):
    note: str = Field(min_length=3, max_length=4000)

@router.post("/{case_id}/notes", status_code=201)
def add_note(case_id: uuid.UUID, b: NoteIn, db=Depends(get_db), user=Depends(require(*WORK))):
    c = db.get(Case, case_id)
    if not c: raise HTTPException(404)
    n = CaseNote(case_id=c.id, author_id=user.id, note=b.note)
    db.add(n); db.flush()
    audit(db, user, "case.note", "case", c.id, None, {"note_id": str(n.id)})
    db.commit()
    return {"id": str(n.id)}

class DispositionIn(BaseModel):
    disposition: str
    rationale: str = Field(min_length=10, max_length=4000)

@router.post("/{case_id}/disposition")
def disposition(case_id: uuid.UUID, b: DispositionIn, db=Depends(get_db), user=Depends(require(*WORK))):
    if b.disposition not in DISPOSITIONS: raise HTTPException(422, f"disposition must be one of {sorted(DISPOSITIONS)}")
    c = db.get(Case, case_id)
    if not c: raise HTTPException(404)
    if c.status in ("closed", "escalated"): raise HTTPException(409, "case already finalised")
    before = {"status": c.status, "disposition": c.disposition}
    if b.disposition == "escalate":
        c.status = "escalated" if user.role in SENIOR else "pending_approval"   # analyst requests, senior approves
    elif b.disposition == "further_review":
        c.status = "in_review"
    else:
        c.status = "closed"; c.closed_at = datetime.now(timezone.utc)
    c.disposition = b.disposition
    final = {"closed": "closed", "escalated": "escalated"}.get(c.status)
    for r in db.scalars(select(CaseAlert).where(CaseAlert.case_id == c.id)):
        if final: db.get(Alert, r.alert_id).status = final
    audit(db, user, "case.disposition", "case", c.id, before, {"status": c.status, "disposition": b.disposition, "rationale": b.rationale})
    db.commit()
    return case_out(c)