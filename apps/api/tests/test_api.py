import uuid

from sqlalchemy import select

from app.models import Alert, AuditEvent
from tests.helpers import send


def make_alert(db):
    tx, *_ = send(db)
    a = Alert(alert_ref="ALT-TEST0001", account_id=tx.source_account_id, transaction_id=tx.id,
              scenario_key="high_velocity", severity="medium", score=0.7,
              reasons_json={"linked_transaction_ids": [str(tx.id)]})
    db.add(a)
    db.commit()
    return a


def test_no_token_is_rejected(client):
    assert client.get("/api/v1/alerts").status_code in (401, 403)


def test_auditor_is_read_only(client, tokens):
    body = {"alert_ids": [str(uuid.uuid4())], "priority": "medium"}
    assert client.post("/api/v1/cases", json=body, headers=tokens["auditor"]).status_code == 403
    # an analyst passes the permission check and only fails because this alert does not exist
    assert client.post("/api/v1/cases", json=body, headers=tokens["analyst"]).status_code == 404


def test_invalid_disposition_is_rejected(client, tokens):
    body = {"disposition": "banana", "rationale": "This is long enough."}
    r = client.post(f"/api/v1/cases/{uuid.uuid4()}/disposition", json=body, headers=tokens["analyst"])
    assert r.status_code == 422


def test_escalation_needs_senior_approval(client, tokens, db):
    alert = make_alert(db)
    r = client.post("/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=tokens["analyst"])
    assert r.status_code == 201
    case_id = r.json()["id"]
    body = {"disposition": "escalate", "rationale": "Pattern matches the layering typology."}
    r = client.post(f"/api/v1/cases/{case_id}/disposition", json=body, headers=tokens["analyst"])
    assert r.json()["status"] == "pending_approval"
    r = client.post(f"/api/v1/cases/{case_id}/disposition", json=body, headers=tokens["senior_investigator"])
    assert r.json()["status"] == "escalated"
    actions = db.scalars(select(AuditEvent.action).where(AuditEvent.entity_type == "case")).all()
    assert "case.create" in actions and "case.disposition" in actions