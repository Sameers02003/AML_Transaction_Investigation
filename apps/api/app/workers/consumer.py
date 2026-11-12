import json, logging, time
from confluent_kafka import Consumer
from prometheus_client import start_http_server, Counter, Histogram
from pydantic import ValidationError
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.kafka import publish
from app.schemas import TransactionIn
from app.modules.ingestion.service import process_transaction, UnknownAccount

log = logging.getLogger("consumer")
PROCESSED = Counter("aml_transactions_processed_total", "Transactions processed")
ALERTS = Counter("aml_alerts_created_total", "Alerts created")
DLQ = Counter("aml_dead_letter_total", "Events sent to dead-letter topic")
E2E = Histogram("aml_event_to_alert_seconds", "Kafka message time to alert creation",
                buckets=(.05, .1, .25, .5, 1, 2, 5, 10, 30))

def handle(msg):
    raw = msg.value().decode()
    try:
        payload = TransactionIn.model_validate_json(raw)
    except ValidationError as e:
        publish("transactions.dlq", msg.key().decode() if msg.key() else "none", {"raw": raw, "error": str(e)}); DLQ.inc(); return
    for attempt in range(3):
        try:
            with SessionLocal() as db:
                _, created, alert = process_transaction(db, payload)
            if created: PROCESSED.inc()
            if alert:
                ALERTS.inc(); E2E.observe(max(0.0, time.time() - msg.timestamp()[1] / 1000))
            return
        except UnknownAccount as e:
            break                                   # retrying cannot fix this
        except Exception as e:                      # transient failure: back off and retry
            log.warning("attempt %s failed: %s", attempt + 1, e); time.sleep(2 ** attempt)
    publish("transactions.dlq", payload.event_id, {"raw": raw, "error": "failed after retries"}); DLQ.inc()

def run():
    logging.basicConfig(level=logging.INFO)
    start_http_server(8001)                         # Prometheus metrics for the worker
    c = Consumer({"bootstrap.servers": settings.kafka_bootstrap, "group.id": "aml-monitor",
                  "auto.offset.reset": "earliest", "enable.auto.commit": False})
    c.subscribe(["transactions.raw"])
    log.info("consumer started")
    while True:
        msg = c.poll(1.0)
        if msg is None: continue
        if msg.error(): log.error(msg.error()); continue
        handle(msg)
        c.commit(msg)                               # commit only after processing or dead-lettering

if __name__ == "__main__":
    run()