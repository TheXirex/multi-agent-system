from sqlalchemy import Engine, create_engine


def create_db_engine(database_url: str) -> Engine:
    """Creates and returns a SQLAlchemy Engine for database connectivity."""
    return create_engine(database_url, pool_pre_ping=True)
