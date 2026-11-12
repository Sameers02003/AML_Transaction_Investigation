import json
from confluent_kafka import Producer
from app.core.config import settings

_producer = None
def get_producer():
    global _producer
    if _producer is None:
        _producer = Producer({"bootstrap.servers": settings.kafka_bootstrap})
    return _producer

def publish(topic: str, key: str, value: dict):
    p = get_producer()
    p.produce(topic, key=key, value=json.dumps(value, default=str))
    p.flush(5)