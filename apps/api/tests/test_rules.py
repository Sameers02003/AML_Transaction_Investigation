from datetime import datetime, timedelta, timezone
from app.schemas import TransactionIn
from app.modules.ingestion.service import process_transaction
from app.modules.rules.engine import run_rules

def send(db, n, src="acct_t_0", dst="acct_t_1", amt="1000.00", minutes_ago=0, eid=None):
    p = TransactionIn(event_id=eid or f"evt_test_{n}", source_account_ref=src, destination_account_ref=dst,
                      amount=amt, currency="INR", channel="IMPS",
                      occurred_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
    return process_transaction(db, p)

def test_velocity_boundary(db):               # exactly at the threshold fires; one below does not
    for i in range(8): send(db, i, minutes_ago=30 - i)
    tx, *_ = send(db, 8, minutes_ago=5)
    assert not [h for h in run_rules(db, tx) if h["rule_key"] == "high_velocity"]   # 9 transfers
    tx, *_ = send(db, 9, minutes_ago=4)
    assert [h for h in run_rules(db, tx) if h["rule_key"] == "high_velocity"]       # 10 transfers

def test_normal_activity_no_alert(db):        # negative case
    _, _, alert = send(db, 1, amt="25000.00")
    assert alert is None

def test_idempotent_replay(db):
    send(db, 1, eid="evt_same_1")
    _, created, alert = send(db, 1, eid="evt_same_1")
    assert created is False and alert is None