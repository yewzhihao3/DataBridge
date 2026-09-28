"""Bounded requests, response headers and a replaceable single-process limiter."""
from collections import OrderedDict, deque
from threading import Lock
from time import monotonic
from starlette.responses import JSONResponse
from app.config import settings


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.attempts = OrderedDict()
        self.lock = Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers += [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                            (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store")]
                if settings.app_env == "production":
                    headers.append((b"strict-transport-security", b"max-age=31536000"))
                message["headers"] = headers
            await send(message)
        if scope["path"] in {"/api/v1/auth/login", "/api/v1/auth/register"} and scope["method"] == "POST":
            host = (scope.get("client") or ("unknown",))[0]
            now = monotonic()
            with self.lock:
                queue = self.attempts.setdefault(host, deque())
                while queue and queue[0] < now - 60:
                    queue.popleft()
                limited = len(queue) >= 30
                if not limited:
                    queue.append(now)
                self.attempts.move_to_end(host)
                while len(self.attempts) > 10000:
                    self.attempts.popitem(last=False)
            if limited:
                return await JSONResponse({"detail":"Too many authentication attempts; try again shortly"}, 429, headers={"Retry-After":"60"})(scope, receive, secure_send)
        # Bound the complete multipart request before Starlette parses/spools it.
        chunks, size = [], 0
        limit = (settings.max_file_size_mb + 1) * 1024 * 1024
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > limit:
                    return await JSONResponse({"detail":"Request too large"}, 413)(scope, receive, secure_send)
                chunks.append(message)
                if not message.get("more_body", False):
                    break
        async def replay():
            if chunks:
                return chunks.pop(0)
            return await receive()
        await self.app(scope, replay, secure_send)
