from sqlalchemy import Engine, create_engine


def create_db_engine(database_url: str) -> Engine:
    """
    Creates and returns a SQLAlchemy Engine for database connectivity.

    Args:
        database_url (str): Connection string for the target database.

    Returns:
        Engine: Configured SQLAlchemy engine instance.
    """
    return create_engine(database_url, pool_pre_ping=True)
