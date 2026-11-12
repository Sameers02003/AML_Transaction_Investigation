import secrets
from fastapi import APIRouter, Depends, Header, HTTPException
from app.core.config import settings
from app.core.db import get_db
from app.core.kafka import publish
from app.schemas import TransactionIn
from app.modules.ingestion.service import process_transaction, UnknownAccount

router = APIRouter(prefix="/transactions", tags=["transactions"])

@router.post("", status_code=202)
def ingest(p: TransactionIn, db=Depends(get_db), x_api_key: str = Header()):
    if not secrets.compare_digest(x_api_key, settings.ingest_api_key):
        raise HTTPException(401, "invalid API key")
    if settings.ingest_mode == "kafka":
        publish("transactions.raw", p.source_account_ref, p.model_dump(mode="json"))
        return {"event_id": p.event_id, "status": "queued"}
    try:
        tx, created, _ = process_transaction(db, p)
    except UnknownAccount as e:
        raise HTTPException(422, str(e))
    return {"event_id": p.event_id, "transaction_id": str(tx.id),
            "status": "processed" if created else "duplicate"}