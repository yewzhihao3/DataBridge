# Milestone 12.5 — SaaS UX & Developer Experience Polish

The authenticated shell is now a single header. The workspace selector remains visible and continues to call the membership-validated workspace switch API. Account actions live in an accessible user menu; Appearance remains in Settings. API health is retained as an unobtrusive status dot.

Invitation links now show a clear workspace, account, invalid/expired, and wrong-account state. Wrong-account users are directed to a safe logout and login flow while the fragment token remains in browser navigation rather than server URLs.

Normal registration still creates an owner workspace. Invitation registration displays and locks the invited email, calls a dedicated server endpoint, and atomically creates the user, membership, invitation acceptance, and active session without creating an additional organization. The server enforces the invitation email and rolls the transaction back if any operation fails. Existing matching users still accept invitations through the existing acceptance endpoint.

Primary buttons use semantic accent tokens with dark-orange text in Orange Dark; disabled buttons use neutral elevated/background tokens rather than faded orange. The same reusable button rules apply throughout the app.

## Development

From the repository root, run `npm run dev`. It starts the FastAPI reload server and Vite with `[backend]` and `[frontend]` log labels. Ctrl+C forwards termination to both child processes. Individual alternatives remain `npm run dev:backend` and `npm run dev:frontend` (or the original commands from their respective folders).

The launcher expects the existing backend virtual environment at `backend/.venv`; it has no root npm dependencies. Browser sessions are cookie-scoped to the browser profile, so authentication is intentionally shared between tabs; workspace context remains validated per request.

## Invitation management and notifications

Workspace owners and administrators can list only their workspace's invitations, refresh their status, and refresh a pending invitation. Refresh creates a new invitation record and expires the old secret, preserving a historical audit trail; accepted invitations cannot be refreshed. Existing secret links are never recoverable from the server, so a new link is copied when an invitation is created or refreshed. The reusable toast host provides stacked, dismissible semantic success/info/warning/error feedback with an accessible live region.
