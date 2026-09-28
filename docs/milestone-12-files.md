# M12 file inventory

Paths are relative to the repository root.

## Added

- `backend/.dockerignore`
- `backend/Dockerfile`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/legacy_schema.py`
- `backend/alembic/m12_schema.py`
- `backend/alembic/script.py.mako`
- `backend/alembic/versions/0001_m11.py`
- `backend/alembic/versions/0002_saas.py`
- `backend/app/models/identity.py`
- `backend/app/routers/auth.py`
- `backend/app/routers/workspaces.py`
- `backend/app/schemas/identity.py`
- `backend/app/security.py`
- `backend/app/services/storage.py`
- `backend/app/tenancy.py`
- `backend/app/web_security.py`
- `backend/claim_workspace.py`
- `backend/scratch/m12_qa_server.py`
- `backend/scratch/verify_m12_copy.py`
- `backend/tests/integration/test_m12_hardening.py`
- `backend/tests/integration/test_migrations.py`
- `backend/tests/integration/test_saas.py`
- `docker-compose.yml`
- `docs/deployment.md`
- `docs/m12-members-qa.png`
- `docs/m12-settings-qa.png`
- `docs/milestone-12-files.md`
- `docs/milestone-12.md`
- `frontend/.dockerignore`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `frontend/src/assets/identity.css`
- `frontend/src/services/session.ts`
- `frontend/src/views/AuthView.vue`
- `frontend/src/views/InviteView.vue`
- `frontend/src/views/SettingsView.vue`

## Modified

- `README.md`
- `backend/.env.example`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/invoice.py`
- `backend/app/models/source_file.py`
- `backend/app/models/template.py`
- `backend/app/routers/analytics.py`
- `backend/app/routers/data_explorer.py`
- `backend/app/routers/exports.py`
- `backend/app/routers/files.py`
- `backend/app/routers/imports.py`
- `backend/app/routers/suggestions.py`
- `backend/app/routers/templates.py`
- `backend/app/schemas/import_batch.py`
- `backend/app/services/export_builder.py`
- `backend/app/services/workbook_inspector.py`
- `backend/requirements.txt`
- `backend/tests/conftest.py`
- `frontend/src/App.vue`
- `frontend/src/components/explorer/InvoiceDetailModal.vue`
- `frontend/src/components/history/ImportDetailsModal.vue`
- `frontend/src/router/index.ts`
- `frontend/src/services/api.ts`
- `frontend/src/types/api.ts`
- `frontend/src/views/ImportHistoryView.vue`
- `frontend/vite.config.ts`
