# Kafka (Redpanda)

Redpanda provides a Kafka-compatible broker through `docker-compose.yml`.

Topics (create once):
`docker compose exec redpanda rpk topic create transactions.raw transactions.dlq -p 3`

- `transactions.raw`: incoming events, keyed by source account
- `transactions.dlq`: malformed events or events that failed after retries

Consumer group: `aml-monitor`. Check lag: `docker compose exec redpanda rpk group describe aml-monitor`