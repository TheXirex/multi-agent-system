from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.database import get_db
from backend.routes import (
    artifacts_router,
    query_router,
    sessions_router,
    upload_router,
)

logger = logging.getLogger("backend.app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ensures database schema and data seeding on service startup.
    """
    logger.info("Starting Backend Gateway Service...")

    try:
        from scripts.generate_data import seed_database
        engine = get_db()
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE SCHEMA IF NOT EXISTS internal;

                ALTER TABLE IF EXISTS public.generated_datasets SET SCHEMA internal;
                ALTER TABLE IF EXISTS public.generated_charts SET SCHEMA internal;
                ALTER TABLE IF EXISTS public.generated_scripts SET SCHEMA internal;
                ALTER TABLE IF EXISTS public.chat_sessions SET SCHEMA internal;
                ALTER TABLE IF EXISTS public.chat_messages SET SCHEMA internal;

                CREATE TABLE IF NOT EXISTS internal.chat_sessions (
                    id VARCHAR(36) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL DEFAULT 'New Chat',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS internal.chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(36) REFERENCES internal.chat_sessions(id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
        seed_database(engine, reset=False)
    except Exception as ex:
        logger.warning(f"Data seeding check or schema init skipped/failed: {ex}")

    yield
    logger.info("Shutting down Backend Gateway Service.")


def create_app() -> FastAPI:
    """
    Creates and configures the FastAPI application instance.
    """
    app = FastAPI(
        title="Backend Gateway Service",
        description="Central backend gateway managing database, sessions, files, and routing requests to AI service.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Enable CORS for frontend flexibility
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register modular route handlers
    app.include_router(sessions_router)
    app.include_router(query_router)
    app.include_router(upload_router)
    app.include_router(artifacts_router)

    return app


app = create_app()
