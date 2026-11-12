# PostgreSQL

Started by `docker-compose.yml` (user, password and database: `aml`; development only).

- Schema is managed with Alembic: `cd apps/api && alembic upgrade head`
- Tests use a separate database: `docker compose exec postgres createdb -U aml aml_test`
- Backup: `docker compose exec postgres pg_dump -U aml aml > backup.sql` (see docs/runbook.md)
- `audit_events` is append-only (database triggers reject updates and deletes)