import logging
from typing import Optional
from sqlalchemy import Engine

from agents.db_agent.config import get_settings as get_db_settings
from agents.db_agent.db import create_db_engine

logger = logging.getLogger("backend.database")

_db_engine: Optional[Engine] = None


def get_db() -> Engine:
    """
    Returns cached database engine for database queries and session management.
    """
    global _db_engine
    if _db_engine is None:
        db_cfg = get_db_settings()
        _db_engine = create_db_engine(db_cfg.database_url)
    return _db_engine
