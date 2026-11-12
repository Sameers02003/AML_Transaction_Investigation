import uuid
from datetime import datetime, timedelta, timezone

from app.modules.ingestion.service import process_transaction
from app.schemas import TransactionIn


def send(db, amt="1000.00", minutes_ago=0, src="acct_t_0", dst="acct_t_1", eid=None):
    p = TransactionIn(event_id=eid or "evt_" + uuid.uuid4().hex[:12], source_account_ref=src,
                      destination_account_ref=dst, amount=amt, currency="INR", channel="IMPS",
                      occurred_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
    return process_transaction(db, p)      # returns (transaction, created, alert)