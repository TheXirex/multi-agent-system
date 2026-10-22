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

                DROP TABLE IF EXISTS public.generated_datasets CASCADE;
                ALTER TABLE IF EXISTS internal.generated_datasets RENAME TO user_datasets;
                ALTER INDEX IF EXISTS internal.idx_generated_datasets_session_id RENAME TO idx_user_datasets_session_id;
                ALTER INDEX IF EXISTS internal.generated_datasets_pkey RENAME TO user_datasets_pkey;
                ALTER SEQUENCE IF EXISTS internal.generated_datasets_id_seq RENAME TO user_datasets_id_seq;

                ALTER TABLE IF EXISTS public.generated_charts SET SCHEMA internal;
                ALTER TABLE IF EXISTS public.generated_scripts SET SCHEMA internal;
                ALTER TABLE IF EXISTS public.chat_sessions SET SCHEMA internal;
                ALTER TABLE IF EXISTS public.chat_messages SET SCHEMA internal;

                CREATE TABLE IF NOT EXISTS internal.user_datasets (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL DEFAULT 'dataset',
                    file_name VARCHAR(255) DEFAULT '',
                    file_path TEXT DEFAULT '',
                    query TEXT,
                    row_count INTEGER DEFAULT 0,
                    columns TEXT[] DEFAULT '{}',
                    data JSONB NOT NULL DEFAULT '[]',
                    session_id VARCHAR(36),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_user_datasets_session_id ON internal.user_datasets(session_id);

                CREATE OR REPLACE VIEW public.user_datasets AS
                SELECT id, name, file_name, file_path, query, row_count, columns, data, session_id, created_at
                FROM internal.user_datasets;

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
