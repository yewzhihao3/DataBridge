# Milestone 12 — Production & SaaS Foundation

M12 adds authentication, workspaces, enforced tenant isolation, memberships,
invitations, versioned migrations, storage and deployment foundations. M1–M11
extraction stays deterministic. No M13 billing, AI, OCR or accounting integrations
were added.

## Architecture and identity

Vue sends same-origin `/api/v1` requests with cookies. FastAPI validates the opaque
session, active user and requested workspace membership before constructing the
business database session. SQLAlchemy applies workspace predicates to all business
queries, including aggregate/projection queries, joins, aliases and relationship
loads. PostgreSQL is the staging target; SQLite remains supported locally.

`User`: integer ID, unique normalized email, Argon2id password hash, display name,
active flag and timestamps. Email is trimmed/lowercased. Passwords have 12–128
characters at registration/change; login accepts the existing password. Inactive
users cannot log in or use an existing session. No password hashes are serialized.
Validation error responses omit Pydantic input/context fields to avoid echoing secrets.

`Organization`: integer ID, name, unique automatically generated slug and timestamps.
Slugs use a normalized name and random suffix to avoid concurrent collision races.
Users never need to enter a slug. Slugs are displayed but are not editable in M12.

`OrganizationMembership`: user and organization foreign keys, role and creation
timestamp, with a unique `(user_id, organization_id)` constraint. Users can join
multiple workspaces; User does not contain a single tenant foreign key.

## Registration, sessions and CSRF

Registration has two steps: Your Account and Your Workspace. The backend atomically
creates the user, organization, OWNER membership and authenticated session. Constraint
failure rolls the transaction back. The browser enters the selected workspace.

The browser receives a random 256-bit opaque `databridge_session` cookie. Only its
SHA-256 hash is stored in `AuthSession`. Cookies use HttpOnly, SameSite=Lax, path `/`,
and Secure in production. There are no bearer tokens in localStorage. Sessions have
an absolute 24-hour default lifetime (configurable 1–168 hours). `/auth/me` restores
user/workspace state. Login replaces the current cookie session; logout deletes it.
Password change revokes all the user's sessions and creates a fresh current session.
There is no access/refresh JWT architecture or sliding-session rotation.

State-changing authenticated requests require `X-CSRF-Token`, matched in constant
time to the session's stored hash, plus origin/Fetch Metadata checks. The token is
derived server-side from the unguessable cookie secret and returned in the typed
session response. It lives only in frontend memory and is restored via `/auth/me`.
Public register/login accept typed JSON and enforce Origin/Fetch Metadata checks;
untrusted cross-origin browser JSON is also blocked by CORS. SameSite is defense in
depth, not the sole CSRF mechanism.

## Active workspace and ownership

The database session record stores the default workspace. Browser API calls also send
`X-Workspace-ID` from the in-memory authenticated state. This pins each tab's requests
to its displayed workspace even if another tab changes the default. Membership is
checked on **every** request; a forged header grants nothing. Switching validates
membership, updates the session default and performs a full document reload, clearing
workflow drafts, modals, outstanding page state and cached tenant results.

| Entity | Ownership |
| --- | --- |
| Template | Explicit, non-null indexed `organization_id`; name unique within workspace |
| SourceFile | Explicit, non-null indexed `organization_id` |
| ImportBatch | Explicit, non-null indexed `organization_id`; parent file/template validated |
| TemplateFieldMapping | Through Template |
| InvoiceRecord / ValidationErrorRecord | Through ImportBatch |
| InvoiceLineItem | Through InvoiceRecord → ImportBatch |
| Invitation / AuditEvent / Membership | Explicit organization foreign key |

Every existing business router uses `get_tenant_db`. Its SQLAlchemy loader criteria
scope both full entities and selected columns. Before-flush checks assign tenant
ownership and reject foreign parents/ownership changes. Tenant sessions forbid bulk
SQL writes; normal ORM instance writes are required. Raw SQL and unrestricted sessions
are reserved for migrations and explicitly scoped identity administration, not business
routes. This is application enforcement, **not PostgreSQL row-level security**.

| API area | Enforcement |
| --- | --- |
| Files / previews | Tenant SourceFile lookup before resolving storage key |
| Templates / mappings | Scoped reads/writes; per-workspace uniqueness |
| Extract / confirm | Both file and template must be visible in the same authorized workspace |
| Import history / detail / delete / record edit | Scoped batches and child predicates |
| Explorer / line items / filter options | Scoped entities, aggregates and related loads |
| Exports / summaries | Scoped export queries and complete scoped custom-field discovery |
| Analytics / rankings | Scoped invoice/item aggregates; soft-deleted batches excluded |
| Smart suggestions / matching | Scoped file and saved-template candidates |
| Audit / members | Explicit organization predicate, with admin authorization for audit/admin actions |

Foreign business object IDs return 404 without revealing existence. Invalid workspace
headers return 403; unauthorized switch targets return 404. Missing/expired/revoked
sessions or inactive accounts return 401. Authorized members without an admin role
receive 403 for administration.

## Roles, invitations and owner safety

MEMBER can use the normal product and view workspace members. ADMIN can manage
non-owner members, invite ADMIN/MEMBER, change workspace settings and read audit events.
OWNER can additionally appoint/manage owners and delete the workspace. Admins cannot
promote anyone to OWNER or manage existing owners. Membership changes serialize on the
organization row, preventing concurrent final-owner removal/downgrade. The final OWNER
cannot be removed or demoted. Membership deletion revokes default sessions for that
workspace; explicit workspace headers are rechecked on subsequent requests.

Workspace deletion is owner-only, requires the exact workspace name, and is unavailable
until the owner belongs to another workspace. The UI asks for confirmation. It deletes
workspace data, memberships, invitations, sessions, audit history and then stored files.
Storage cleanup failure is logged and may require operator cleanup; database deletion
is already committed. Backups and retention policies are essential before staging use.

Invitations contain a hashed random token, bound organization and normalized email,
ADMIN/MEMBER role, seven-day expiry, creator and acceptance timestamp. Creation returns
a copyable URL; there is no outbound email service. The token uses a URL fragment to
avoid web access-log exposure. Acceptance atomically claims the invitation once,
checks the authenticated email, adds membership and changes the active workspace.
Existing members keep their role; an invitation does not silently downgrade/upgrade them.

Existing users log in, then accept. New users complete the same account/workspace
registration flow and return to the invitation. Their first workspace is retained;
the invited workspace becomes active after acceptance. Expired, reused and wrong-email
tokens are rejected. Email verification/password recovery are not part of M12.

## Migrations and existing data

Alembic replaces startup `create_all` as the schema evolution mechanism. Startup
checks the applied revision; it never creates or alters tables. `0001_m11` freezes the
M11 schema, creates a fresh database or validates/adopts an existing complete schema.
`0002_saas` adds identity tables, creates Default Workspace, backfills tenant IDs and
changes template uniqueness. Child rows remain unchanged. SQLite uses batch table
reconstruction and explicit DDL transactions, with foreign-key validation. Frozen
metadata is kept under `alembic/`; migrations do not import mutable application models.

An M11 reload process may have created empty identity tables before the old startup
hook was removed. M12 adopts these only when columns and constraints exactly match
and the tables are empty. Populated/incompatible partial schemas require operator review.

Default Workspace starts unclaimed. Register normally, then use the trusted local
`python claim_workspace.py owner@example.com` command. It only grants ownership when
the default workspace has no memberships. Public registration cannot claim legacy data.
The historical `migrate.py` remains for pre-M12 upgrades; do not use it on M12 databases.

Fresh and pre-M12 snapshot upgrades are tested. A temporary read-only-source copy of
the actual development database also preserved **every existing column value**:
7 templates, 68 mappings, 59 source files, 28 import batches, 51 invoices, 86 line
items and 8 validation records. All tenant IDs were backfilled and foreign keys passed.
The original development database was not migrated by the verification script.

## PostgreSQL and deployment

Models use portable Numeric/Decimal, JSON, Date/DateTime, foreign keys, uniqueness and
indexes. Dates are UTC-naive in persistence; set the database server timezone to UTC.
PostgreSQL table/index DDL compilation is tested. **No live PostgreSQL integration run
was performed**: Docker is installed but its daemon is unavailable. No cloud staging
deployment was created. See [deployment.md](deployment.md) for the private staging runbook.

Dockerfiles and Compose define nginx/Vue, FastAPI and PostgreSQL with persistent volumes.
The local stack binds only localhost:8080; production requires an HTTPS proxy, secure
cookie configuration, explicit CORS origins and environment-supplied database secrets.
No embedded development signing secret is needed for opaque sessions.

## Storage, security and audit

`StorageBackend` defines generated keys, private local materialization, promotion and
deletion. `LocalStorageBackend` is the active implementation. File, extraction and
suggestion routers resolve storage keys through it. An object-storage adapter remains
future work. Uploads stream to generated temporary files, then promote to generated
final keys; failures roll back metadata and clean up created files.

Uploads check extension, magic bytes, workbook readability, 10 MB default compressed
size, archive entry count, expanded size (100 MB total / 30 MB per entry), compression
ratio, encryption, worksheet count and dimensions. Inspection is limited to 100 sheets,
100,000 rows, 512 columns and 2 million rectangular cells per sheet. The complete HTTP
body is bounded before multipart parsing. There is no malware scanner, process sandbox
or hard parser CPU timeout; memory/CPU quotas at deployment remain necessary.

Headers include no-store, nosniff, frame denial and no-referrer; HTTPS production adds
HSTS. Nginx adds CSP. Login/register have a bounded single-process peer-IP limiter,
designed to be replaced/complemented by an edge limiter before public scale. Error
responses no longer expose database exception text. Production disables OpenAPI/docs
and rejects insecure cookie/origin settings. CORS uses explicit allowed origins.

Workspace audit events cover registration, login/logout, password changes, template
creation/update/deletion, import confirmation/deletion, invoice edits, exports,
invitations/acceptance, member role/removal and workspace changes. Events store action,
actor, entity type/ID and minimal metadata; no passwords, raw session/invitation tokens,
workbook contents or exports are stored. Ordinary reads/page views are not logged.
The settings Audit tab displays the latest 100 events; the API supports offset paging.

## Settings and deferred-debt fixes

Settings includes Account, Workspace, Members, Appearance, and admin-only Audit.
Account supports display-name changes, email display and password changes. Workspace
supports name editing, another workspace and owner-only deletion. Members supports
listing, roles, removal and copyable invitations. Appearance reuses all existing theme
families and Light/Dark/System settings, still localStorage-backed.

- Missing company/invoice identifiers now block confirmation instead of fabricating
  “Unknown Company”/“Unknown Invoice”. Existing non-null schema and old records remain
  unchanged; historical placeholders cannot be reliably inferred and are not rewritten.
- CSV dangerous **text** prefixes are escaped; typed negative numbers stay numeric.
  XLSX text cells are explicitly string-typed, including headers and untrusted custom fields.
- Export column discovery scans every matching custom-field dictionary, not 200 samples.
- XLSX autofilter is set after data rows are written.
- Frontend `invoice_id` and Decimal response unions match backend responses; edit forms
  explicitly convert amount values to numbers.
- Import History totals come from a workspace-scoped server summary, not the loaded page.
  Search/status controls still filter the loaded page; full server-side search is deferred.
- Duplicate detection ignores soft-deleted imports and is workspace scoped.

## Verification and limitations

Baseline: **249 passed, 2 warnings**. Full M12 regression: **273 passed, 2 warnings**.
The warnings are the existing Starlette HTTP 422 constant deprecations. Frontend
`npm run build` passes Vue type checking and Vite production bundling.

New tests exercise auth lifecycle, inactive/expired sessions, CSRF, rollback, role
rules, final-owner protection, invitations, forged workspace headers, cross-tenant
detail/edit/delete, mixed extraction IDs, files/previews, suggestions/template matching,
exports, filters, audit/members, and exact isolated analytics (100 versus 1,000,000).
They also cover migrations, Decimal DDL compilation, archive limits, path traversal,
formula safety, autofilter bounds, >200-row custom discovery, soft-deleted duplicates,
history totals, owner deletion and auth rate limiting. Existing 249 regressions remain.

Manual browser QA used only `scratch/m12-qa.sqlite` and QA uploads, separate from demo
data. Verified two-step registration, automatic entry, successful/failed login, logout,
workspace creation/switching, account/workspace/member settings, copyable invitation
creation, new-user invitation acceptance into the intended workspace, MEMBER controls, all six theme family/mode combinations and mobile/tablet overflow checks.
Automated role/invite tests remain the authoritative negative-permission checks.

Remaining production limitations: no live PostgreSQL/Docker/staging execution; no email
verification, recovery mail or delivery; single-process rate limiting; no distributed
session cache or cleanup scheduler; no malware scanning/parser isolation; in-memory
exports and complete custom-field discovery can be expensive on large workspaces;
local storage only; no database RLS; audit retention is tied to workspace lifetime.
These are explicit staging prerequisites/limits, not claims of public-production readiness.

## File inventory

Added: identity models/schemas, auth/workspace routers, security/tenancy/middleware,
storage service, Alembic configuration/frozen schemas/revisions/template, local claim
command, migration/security regression suites, isolated QA/verification scripts,
backend/frontend Dockerfiles and ignores, nginx/Compose, session state, auth/invite/
settings Vue views, identity styles, this report, deployment guide and QA screenshot.

Modified: configuration/environment example, application startup/router registration,
top-level business models, every business router dependency, invoice update validation,
workbook inspector/export builder, requirements/test fixtures, frontend app/router/API,
numeric response types and invoice edit forms, history summaries, Vite proxy and README.

See the [exact file inventory](milestone-12-files.md) for all added and modified paths.
