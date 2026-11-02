import os
from typing import Optional
import psycopg2


def clear_langfuse_data(db_url: Optional[str] = None) -> None:
    """Truncates Langfuse traces, sessions, scores, and datasets while preserving projects and auth keys."""
    resolved_url = db_url or os.getenv("LANGFUSE_DB_URL", "postgresql://postgres:postgres@localhost:5432/langfuse")
    conn = psycopg2.connect(resolved_url)
    conn.autocommit = True
    cur = conn.cursor()

    tables = [
        "scores",
        "observations",
        "observation_media",
        "trace_media",
        "traces",
        "trace_sessions",
        "dataset_run_items",
        "dataset_runs",
        "dataset_items",
        "datasets",
        "comments",
        "events",
    ]

    existing_tables = []
    for tbl in tables:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s;",
            (tbl,),
        )
        if cur.fetchone():
            existing_tables.append(tbl)

    if existing_tables:
        table_list = ", ".join(f'"{t}"' for t in existing_tables)
        cur.execute(f"TRUNCATE TABLE {table_list} CASCADE;")
        print(f"Truncated Langfuse telemetry tables: {', '.join(existing_tables)}.")
    else:
        print("No Langfuse telemetry tables found to truncate.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    clear_langfuse_data()

