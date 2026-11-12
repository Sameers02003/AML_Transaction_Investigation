from sqlalchemy import select

from app.models import Alert
from app.modules.rules.engine import run_rules
from tests.helpers import send


def keys(db, tx):
    return {h["rule_key"] for h in run_rules(db, tx)}


def test_structuring_boundary(db):
    send(db, amt="44999.99", minutes_ago=40)            # just below the band, not counted
    send(db, amt="45000.00", minutes_ago=30)
    tx, *_ = send(db, amt="47000.00", minutes_ago=20)
    assert "possible_structuring" not in keys(db, tx)   # only 2 transfers in the band
    tx, *_ = send(db, amt="49000.00", minutes_ago=10)
    assert "possible_structuring" in keys(db, tx)       # the third one


def test_window_61_minutes_is_outside(db):
    send(db, minutes_ago=61)
    for i in range(8):
        send(db, minutes_ago=30 - i)
    tx, *_ = send(db, minutes_ago=0)
    assert "high_velocity" not in keys(db, tx)          # only 9 inside the 60-minute window


def test_window_59_minutes_is_inside(db):
    send(db, minutes_ago=59)
    for i in range(8):
        send(db, minutes_ago=30 - i)
    tx, *_ = send(db, minutes_ago=0)
    assert "high_velocity" in keys(db, tx)              # 10 inside the window


def test_alert_deduplication(db, low_threshold, no_ml):
    for i in range(12):
        send(db, minutes_ago=40 - 3 * i)
    alerts = db.scalars(select(Alert)).all()
    assert len(alerts) == 1
    assert len(alerts[0].reasons_json["linked_transaction_ids"]) >= 2