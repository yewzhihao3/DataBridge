"""
app/main.py — FastAPI Application Entrypoint.

Sets up middleware, CORS, lifespan hooks, database table initialization,
and registers all API routers.
"""

from contextlib import asynccontextmanager
import logging
import time
import uuid
from sqlalchemy import text
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.web_security import SecurityMiddleware
from app.routers.analytics import router as analytics_router
from app.routers.suggestions import router as suggestions_router
from app.routers.batch_imports import router as batch_imports_router
from app.routers.documents import router as documents_router
from app.database import engine
from app.routers.auth import router as auth_router
from app.routers.workspaces import router as workspaces_router
from app.routers import (
    data_explorer_router,
    exports_router,
    files_router,
    imports_router,
    templates_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for startup and shutdown tasks.
    """
    # 1. Ensure upload storage directory exists
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    # 2. Verify secure deployment and versioned schema; never mutate schema here.
    settings.validate_production_security()

    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if revision != "0006_receipt_records":
            raise RuntimeError("Run alembic upgrade head before starting DataBridge")

    yield
    # Shutdown tasks (if any) go here


def create_app() -> FastAPI:
    """
    Application factory creating and configuring the FastAPI app instance.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=None if settings.app_env == "production" else "/docs",
        openapi_url=None if settings.app_env == "production" else "/openapi.json",
        redoc_url=None if settings.app_env == "production" else "/redoc",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.trusted_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(SecurityMiddleware)

    @app.middleware("http")
    async def request_log(request, call_next):
        """Emit safe, correlation-friendly request logs without request data."""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger("databridge.request").exception(
                "request_failed request_id=%s method=%s path=%s",
                request_id, request.method, request.url.path,
            )
            raise
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("databridge.request").info(
            "request request_id=%s method=%s path=%s status=%s duration_ms=%d",
            request_id, request.method, request.url.path, response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default input/ctx fields can echo passwords or workbook data.
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]})

    # Router registration
    app.include_router(auth_router)
    app.include_router(workspaces_router)
    app.include_router(files_router)
    app.include_router(templates_router)
    app.include_router(imports_router)
    app.include_router(data_explorer_router)
    app.include_router(exports_router)
    app.include_router(analytics_router)
    app.include_router(suggestions_router)
    app.include_router(batch_imports_router)
    app.include_router(documents_router)

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        """
        Health check endpoint for monitoring and test verification.
        """
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
        }

    return app


app = create_app()
