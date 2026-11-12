from datetime import datetime, timezone
from pprint import pprint

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Account
from app.modules.graph.signals import graph_signals

with SessionLocal() as db:
    for ref in ["acct_mule_01", "acct_mule_02"]:
        acct = db.scalar(select(Account).where(Account.account_ref == ref))
        score, evidence = graph_signals(db, acct.id, datetime.now(timezone.utc))
        print(ref, "graph score:", score)
        pprint(evidence)