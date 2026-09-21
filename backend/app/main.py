"""
app/main.py — FastAPI Application Entrypoint.

Sets up middleware, CORS, lifespan hooks, database table initialization,
and registers all API routers.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import files_router, imports_router, templates_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for startup and shutdown tasks.
    """
    # 1. Ensure upload storage directory exists
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    # 2. Ensure all ORM tables are created in SQLite/Postgres
    Base.metadata.create_all(bind=engine)

    yield
    # Shutdown tasks (if any) go here


def create_app() -> FastAPI:
    """
    Application factory creating and configuring the FastAPI app instance.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Router registration
    app.include_router(files_router)
    app.include_router(templates_router)
    app.include_router(imports_router)

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
