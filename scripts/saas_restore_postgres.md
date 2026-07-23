# PostgreSQL restore

1. Stop `saas-api`, `saas-worker`, and `saas-scheduler` while keeping PostgreSQL running.
2. Verify the target database and take a fresh backup.
3. Provide credentials through `DATABASE_URL` or `PGPASSWORD`; never place passwords in this document or command history.
4. Restore with `pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" <backup.dump>`.
5. Run `python scripts/saas_migrate.py` to apply `alembic upgrade head`.
6. Start API, Worker, and Scheduler, then verify `/api/ready` and the service heartbeat endpoints.

Restore is destructive for the selected target database. Never point this procedure at a database until its identity and backup have been verified.
