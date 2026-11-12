from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import Transaction, Account
from app.modules.monitoring.service import evaluate

class UnknownAccount(Exception):
    pass

def process_transaction(db, p):
    """Returns (transaction, created: bool, alert | None). Safe to call twice with the same event_id."""
    existing = db.scalar(select(Transaction).where(Transaction.event_id == p.event_id))
    if existing:
        return existing, False, None
    refs = {a.account_ref: a for a in db.scalars(select(Account).where(
        Account.account_ref.in_([p.source_account_ref, p.destination_account_ref])))}
    src, dst = refs.get(p.source_account_ref), refs.get(p.destination_account_ref)
    if not src or not dst:
        raise UnknownAccount(f"unknown account in event {p.event_id}")
    tx = Transaction(event_id=p.event_id, source_account_id=src.id, destination_account_id=dst.id,
                     amount=p.amount, currency=p.currency, channel=p.channel, occurred_at=p.occurred_at)
    alert = None
    try:
        db.add(tx)
        db.flush()
        alert = evaluate(db, tx)
        db.commit()
    except IntegrityError:   # same event arrived twice at once; DB unique constraint is the authority
        db.rollback()
        return db.scalar(select(Transaction).where(Transaction.event_id == p.event_id)), False, None
    return tx, True, alert