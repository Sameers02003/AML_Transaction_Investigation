# Runbook

## Start everything
1. Open Docker Desktop, then `docker compose up -d` in the project root.
2. API: `cd apps/api`, activate `.venv`, `uvicorn app.main:app --reload --host 0.0.0.0`
3. Consumer: same folder, `python -m app.workers.consumer`
4. Web: `cd apps/web`, `npm run dev`

## Check health
- `localhost:8000/health`, `localhost:9090/targets`, Grafana at `localhost:3000`
- Queue lag: `docker compose exec redpanda rpk group describe aml-monitor`

## Dead-letter events
`docker compose exec redpanda rpk topic consume transactions.dlq -n 5`
Fix the cause, then re-send corrected events through the API. Event IDs make re-sending safe.

## Replay
Stop the consumer, run `rpk group seek aml-monitor --to start` (see `rpk group seek --help`), start the consumer. Duplicates are ignored by event ID, so replaying is safe but does not re-score old events.

## Roll back a rule
Rules are versioned and never edited in place. On the Scenarios page, save the older parameters as a new version.

## Roll back a model
Copy an older `ml/model_artifacts/iforest-*.joblib` over `current.joblib`, then restart the API and consumer.

## Backup and restore
`docker compose exec postgres pg_dump -U aml aml > backup.sql`, then restore into a scratch database and compare row counts. Last drill: (write the date here).