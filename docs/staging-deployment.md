# Private staging deployment

This runbook deploys DataBridge as a private staging environment, not a public
launch. It uses **Render**: a Static Site for Vue, one Docker Web Service for
FastAPI, Render PostgreSQL, and a private persistent disk mounted on the API
service. This is intentionally a small, understandable architecture with no
Kubernetes, worker fleet, Redis, object store, or email service.

```text
Browser -- HTTPS --> Render Static Site (Vue)
                     |
                     +-- HTTPS/CORS --> Render Web Service (FastAPI + disk)
                                              |
                                              +--> Render PostgreSQL
```

The separate frontend lets Render serve static files cheaply; the API needs a
web service because uploads must be kept on its attached private disk. The
frontend is built with the API's public HTTPS URL, while the API allows only
the frontend's exact HTTPS origin. Render-provided `*.onrender.com` names are
fine for staging; custom domains are optional.

## Deploy DataBridge staging from scratch

1. Create a Render account and connect the GitHub repository. Keep the Render
   project private and use **demo data only**.
2. Create a Render PostgreSQL database in the same region as the web service.
   Copy its **internal** connection string into the backend service as
   `DATABASE_URL`. Do not put it in Git or in the frontend.
3. Create a Docker Web Service from this repository with root directory
   `backend`. Attach a persistent disk at `/var/data/databridge` (at least the
   size of your staging test pack plus database backups). Its normal start
   command is `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-proxy-headers`.
   Do not enable reload and do not expose the disk as a static directory.
4. Set the backend environment variables listed below. Initially use a chosen
   placeholder frontend URL; after creating the frontend, replace it with its
   exact Render URL and redeploy the API.
5. Run the release/pre-deploy command **once per deploy**:
   `alembic upgrade head`. If it fails, stop the release; read the migration
   output and current revision before retrying. The application will refuse to
   start on a revision other than `0003_batch_imports`.
6. Create a Render Static Site with root directory `frontend`, build command
   `npm ci && npm run build`, and publish directory `dist`. Set its build-time
   environment variable `VITE_API_BASE_URL` to the API's exact HTTPS URL, for
   example `https://databridge-api-staging.onrender.com` (no trailing slash).
7. Set the backend `FRONTEND_URL` and `CORS_ORIGINS` to the exact Static Site
   HTTPS URL, redeploy both services, then open the frontend URL in a normal
   browser and an incognito browser.
8. Register a new staging account. Normal registration creates the user,
   organization, and OWNER membership; no database insert or legacy workspace
   claim is needed for a clean database.

## Backend environment variables

Use Render's encrypted environment settings. The values below are examples,
not values to commit.

| Variable | Staging value / purpose |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Render internal PostgreSQL SQLAlchemy URL, beginning `postgresql+psycopg://` |
| `FRONTEND_URL` | Exact HTTPS Static Site origin |
| `CORS_ORIGINS` | JSON array containing only that exact frontend origin |
| `COOKIE_SECURE` | `true` |
| `SESSION_HOURS` | `24` unless a different staging lifetime is needed |
| `UPLOAD_DIR` | `/var/data/databridge/uploads` |
| `MAX_FILE_SIZE_MB` | `10` (keep proxy limits aligned) |
| `LOG_LEVEL` | `INFO` |
| `DEV_PUBLIC_ORIGINS` | **unset** |

`VITE_API_BASE_URL` belongs only to the frontend build. It is public by design,
so never put a password, database URL, or API secret in it. The frontend has
no `localhost` production fallback when this variable is set.

The API fails closed in production unless cookies are secure, the frontend URL
is HTTPS, and every trusted CORS origin is an explicit HTTPS origin. Cookie
sessions are `HttpOnly`, `Secure`, and `SameSite=Lax`; state-changing requests
also require the CSRF token and a trusted Origin. Do not use `*`, disable CSRF,
or weaken origin checks to fix a deployment problem.

## Migrations, health, logs, and rollback

Before each release, inspect the current schema with:

```sh
cd backend
alembic current
alembic upgrade head
alembic current
```

The Docker image starts only the ASGI server; it never runs migrations itself.
This prevents multiple application instances from racing a schema migration.
Never auto-downgrade staging. If a migration fails or is unsafe, keep the
previous application version and restore a tested database backup if needed.

Configure Render's health check as `GET /health`. It returns minimal service
metadata only. Render deploy status, service logs, PostgreSQL status, and this
health check are sufficient monitoring for M14. Request logs include a request
ID, method, path, status, and duration; they intentionally omit passwords,
cookies, invitation tokens, workbook contents, and exports. The existing auth
limiter is single-process and suitable only for this private staging service.

To roll back, use Render's previous Static Site deploy and previous Web Service
deploy independently. Do not roll back the database by Alembic downgrade unless
a migration explicitly documents that it is safe. Prefer restoring the matched
database and file-storage backup, then verify `alembic current` before serving
traffic.

## Backups and recovery

Enable Render PostgreSQL backups/snapshots available to the selected plan. Also
periodically take a logical backup from a trusted machine:

```sh
pg_dump --format=custom --no-owner --file=databridge-staging.dump "$DATABASE_URL"
```

Back up the persistent disk's `uploads` directory at the same time and retain
the database dump and file backup as a pair. Storage keys are generated by the
backend and files remain private; never publish the disk or copy user filenames
into paths. To recover: place the matching files under `UPLOAD_DIR`, restore
the PostgreSQL dump to an empty replacement database, point `DATABASE_URL` to
it, run `alembic current`, and only then start the API and verify `/health`.

## Staging QA and common failures

Run the full M14 checklist after deployment: registration/login/logout/refresh,
two-workspace isolation, XLSX single and batch imports, pending review,
templates, explorer, CSV/XLSX exports, dashboard filters, settings/audit,
themes, and copied invitation acceptance from incognito or another browser.
Use the Jan–Dec demo XLSX pack only. Confirm organization A cannot discover
organization B's records, files, templates, filters, exports, invitations, or
audit events. Validate PostgreSQL Decimal analytics, JSON `custom_fields`,
foreign keys, and the current Alembic revision with representative tests.

If login does not persist, check that both URLs are HTTPS, `COOKIE_SECURE=true`,
the exact frontend origin is in `CORS_ORIGINS`, and the browser is sending the
session cookie to the API. If CORS/CSRF fails, compare the browser Origin header
with `FRONTEND_URL`; do not add a wildcard. If uploads disappear, verify that
`UPLOAD_DIR` is below the mounted disk and that the disk is attached to the
running backend service. If startup says migrations are missing, run
`alembic current` and complete the release migration before restarting.

## Private-access and security notes

If the Render plan supports it, enable platform access control or an edge basic
auth gate for the frontend and API, then confirm it does not strip cookies or
block invitation fragments. This is optional; DataBridge's own authentication
remains required. Keep secrets only in Render settings or ignored `.env` files,
rotate any accidentally exposed secret, and periodically scan the repository
before deployment. Existing HTTPS headers remain enabled, including no-store,
nosniff, frame denial, referrer policy, HSTS in production, and the frontend
CSP. Email invitation delivery, OCR, AI, billing, public launch, and
public-scale rate limiting are intentionally out of scope.
