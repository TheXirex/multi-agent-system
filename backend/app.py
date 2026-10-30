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
    """Initializes internal database schemas and seeds baseline tables on service startup."""
    logger.info("Starting Backend Gateway Service...")

    try:
        from scripts.load_data import seed_database

        engine = get_db()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE SCHEMA IF NOT EXISTS internal;

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

                    CREATE TABLE IF NOT EXISTS internal.change_history (
                        id SERIAL PRIMARY KEY,
                        session_id VARCHAR(36) NOT NULL,
                        action_type VARCHAR(50) NOT NULL,
                        table_name VARCHAR(255) NOT NULL,
                        description TEXT,
                        executed_sql TEXT NOT NULL,
                        rollback_sql TEXT,
                        before_state JSONB DEFAULT '[]',
                        after_state JSONB DEFAULT '[]',
                        is_reverted BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_change_history_session_id
                        ON internal.change_history(session_id);

                    CREATE TABLE IF NOT EXISTS internal.generated_charts (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(255),
                        chart_type VARCHAR(50),
                        spec JSONB NOT NULL,
                        dataset_id INTEGER,
                        session_id VARCHAR(36),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_generated_charts_session_id
                        ON internal.generated_charts(session_id);

                    CREATE TABLE IF NOT EXISTS internal.generated_scripts (
                        id SERIAL PRIMARY KEY,
                        script TEXT NOT NULL,
                        language VARCHAR(50) DEFAULT 'python',
                        task_description TEXT,
                        dataset_id INTEGER,
                        session_id VARCHAR(36),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_generated_scripts_session_id
                        ON internal.generated_scripts(session_id);
                    """
                )
            )
        seed_database(engine, reset=False)
    except Exception as ex:
        logger.warning(f"Data seeding check or schema init skipped/failed: {ex}")

    yield
    logger.info("Shutting down Backend Gateway Service.")


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application instance."""
    app = FastAPI(
        title="Backend Gateway Service",
        description="Central backend gateway managing database, sessions, files, and routing requests to AI service.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(sessions_router)
    app.include_router(query_router)
    app.include_router(upload_router)
    app.include_router(artifacts_router)

    return app


app = create_app()
