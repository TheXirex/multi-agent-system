import logging
from typing import Any, List, Optional
from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)


def get_session_schema_name(session_id: str) -> str:
    """Constructs a safe, deterministic PostgreSQL schema identifier for a session."""
    clean_id = "".join(c if c.isalnum() else "_" for c in str(session_id).lower().strip())
    return f"session_{clean_id}"


def ensure_session_replica(engine: Engine, session_id: str) -> str:
    """
    Ensures an isolated PostgreSQL schema replica exists for the given session.
    If it does not exist yet, clones all baseline tables and data from 'public'.
    """
    if not session_id:
        return "public"

    schema_name = get_session_schema_name(session_id)

    with engine.begin() as conn:
        schema_exists = conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
            {"s": schema_name},
        ).scalar()

        if schema_exists:
            return schema_name

        logger.info(f"Creating isolated session replica schema: '{schema_name}' for session '{session_id}'")
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))

        # 1. Discover all base tables in 'public' (excluding views)
        base_tables: List[str] = [
            row[0]
            for row in conn.execute(
                text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    ORDER BY table_name ASC
                """)
            ).fetchall()
        ]

        # 2. Clone structure and baseline records for each table
        for tbl in base_tables:
            try:
                conn.execute(
                    text(
                        f'CREATE TABLE IF NOT EXISTS "{schema_name}"."{tbl}" '
                        f'(LIKE public."{tbl}" INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)'
                    )
                )
                conn.execute(
                    text(f'INSERT INTO "{schema_name}"."{tbl}" SELECT * FROM public."{tbl}" ON CONFLICT DO NOTHING')
                )
            except Exception as ex:
                logger.warning(f"Error cloning baseline table '{tbl}' into '{schema_name}': {ex}")

    logger.info(f"Session replica schema '{schema_name}' successfully provisioned.")
    return schema_name


def drop_session_replica(engine: Engine, session_id: str) -> bool:
    """Drops the isolated session schema and all its cloned or user-created tables permanently."""
    if not session_id:
        return False

    schema_name = get_session_schema_name(session_id)
    logger.info(f"Dropping session replica schema: '{schema_name}' for session '{session_id}'")

    try:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        logger.info(f"Session replica schema '{schema_name}' successfully dropped.")
        return True
    except Exception as ex:
        logger.error(f"Failed to drop session replica schema '{schema_name}': {ex}", exc_info=True)
        return False


def get_session_schema_or_public(session_id: Optional[str]) -> str:
    """Returns the session schema name if session_id is provided, otherwise falls back to 'public'."""
    if session_id:
        return get_session_schema_name(session_id)
    return "public"


def apply_session_search_path(conn: Any, session_id: Optional[str]) -> None:
    """Sets search_path for the active database connection to prioritize the session replica schema."""
    if session_id:
        schema_name = get_session_schema_name(session_id)
        conn.execute(text(f'SET search_path TO "{schema_name}", internal, public'))
    else:
        conn.execute(text("SET search_path TO public, internal"))
