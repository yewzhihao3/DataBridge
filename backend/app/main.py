"""
app/main.py — FastAPI Application Entrypoint.

Sets up middleware, CORS, lifespan hooks, database table initialization,
and registers all API routers.
"""

from contextlib import asynccontextmanager
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
    if settings.app_env == "production" and (settings.dev_public_origins.strip() or not settings.cookie_secure or not settings.frontend_url.startswith("https://") or "*" in settings.trusted_origins):
        raise RuntimeError("Production requires HTTPS, secure cookies and explicit CORS origins")

    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if revision != "0003_batch_imports":
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
