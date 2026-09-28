# Private staging deployment

M12 adds a single FastAPI service, Vue frontend, PostgreSQL and persistent local
upload storage. No billing, external AI, email delivery or cloud provider is required.

## Local development

From `backend`, install `requirements-dev.txt` (which includes production requirements)
into your virtual environment, then run:

```sh
alembic upgrade head
uvicorn app.main:app --reload
```

From `frontend`, run `npm ci` and `npm run dev`. Vite proxies `/api` and `/health` to
`http://127.0.0.1:8000`; set `BACKEND_URL` for another local backend. The browser always
uses relative `/api/v1` URLs. Keep frontend and API on one public origin in staging.
Schema changes never run implicitly at application startup.

## Configuration

Copy `backend/.env.example` for native development. Environment values override it.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | `sqlite:///./databridge.db` locally; `postgresql+psycopg://user:password@host/database` in staging |
| `APP_ENV` | `production` in HTTPS staging; disables interactive API docs |
| `FRONTEND_URL` | Exact public HTTPS origin; used for invitation links and origin checks |
| `CORS_ORIGINS` | JSON array of exact allowed origins; no wildcard in production |
| `COOKIE_SECURE` | `true` for HTTPS staging; false only for HTTP localhost |
| `SESSION_HOURS` | Absolute session lifetime, default 24 hours |
| `UPLOAD_DIR` | Persistent, private directory writable by backend user |
| `MAX_FILE_SIZE_MB` | Default 10; also align reverse proxy body limit |

No signing secret is needed for opaque random database-backed sessions. Database
credentials are secrets and must come from environment or a deployment secret store.
Do not commit `.env`, user databases, uploads, session cookies or invitation links.
Use URI-escaped credentials in database URLs.

## Docker

Create a root `.env` containing a newly generated `POSTGRES_PASSWORD` (use a long
URL-safe random value). Then run:

```sh
docker compose up --build
```

The UI is bound to `http://localhost:8080` on loopback only. Database and backend
ports are internal. Named volumes persist PostgreSQL and uploaded files. PostgreSQL
health precedes backend migration/startup. This local stack deliberately uses HTTP
development cookies. For staging, put an HTTPS reverse proxy in front, configure
`APP_ENV=production`, `COOKIE_SECURE=true`, `FRONTEND_URL=https://your-host` and matching
`CORS_ORIGINS`. Apply migrations as a single deployment job before starting multiple
workers; do not race migration processes. Keep uploads shared if using multiple hosts.

The backend ignores forwarded headers by default. The in-process login limiter is
per direct peer and single worker. Before public exposure, configure a trusted edge
proxy with per-client limits and trusted proxy addressing. Never trust arbitrary
`X-Forwarded-For` from the internet. There is no distributed limiter in M12.

## Existing M11 database

1. Stop writers. Back up the database **and** its matching upload directory.
2. Verify that the database is at the complete M11 schema. Older partial schemas
   must first be upgraded using the historical migration process on a backup copy.
3. Run `alembic upgrade head`. The baseline adopts existing M11 tables; M12 creates
   `Default Workspace`, backfills all files/templates/import batches, and changes
   template uniqueness to `(organization_id, name)`. Child ownership follows parents.
4. Register an account normally. From a trusted local terminal, run
   `python claim_workspace.py owner@example.com`. This grants that registered active
   account OWNER of the unclaimed default workspace. A second claim is rejected.
5. Log in again, select Default Workspace and verify records and files before enabling writes.

No public registration can claim migrated data. Migration downgrade is intentionally
disabled; rollback means restoring a verified backup. Do not run the old `migrate.py`
against an M12 database. Keep migration revisions immutable after deployment.

## Backups and operational checks

- Use PostgreSQL backups (`pg_dump` or managed snapshots) with matching storage backups.
  Test restores, including workspace memberships and file previews.
- Keep storage inaccessible to direct HTTP requests; files are resolved only after
  tenant authorization. Do not serve `UPLOAD_DIR` through nginx.
- Enforce HTTPS; check Secure/HttpOnly/SameSite=Lax cookies in the browser.
- Verify registration, session restoration, cross-workspace 404s and exports on staging.
- Monitor disk, database growth, request errors and migration failure logs. Remove
  expired session/invitation rows with a reviewed maintenance job as volume grows.
- Workspace deletion permanently removes its data and audit history; establish a
  retention/backup policy appropriate to the deployment before enabling public use.

## Verification status

Compose configuration validation passes (`docker compose config --quiet`).
SQLite fresh and preserved-M11 upgrades are integration-tested, including foreign keys.
PostgreSQL DDL is compiled in tests. Live PostgreSQL and the Docker stack have **not**
been run in this environment: Docker's daemon is unavailable. Run the representative
auth, isolation, Decimal aggregation, JSON, export and migration checks against a
dedicated PostgreSQL database before calling this production verified.
