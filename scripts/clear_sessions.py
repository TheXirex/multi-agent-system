import os
from pathlib import Path
from typing import Optional
import psycopg2


def clear_all_sessions(db_url: Optional[str] = None) -> None:
    """Drops isolated session schemas and truncates chat session tables in PostgreSQL."""
    resolved_url = db_url or os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/app_db")
    conn = psycopg2.connect(resolved_url)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'session_%';")
    schemas = [r[0] for r in cur.fetchall()]
    for s in schemas:
        cur.execute(f'DROP SCHEMA IF EXISTS "{s}" CASCADE;')
    print(f"Dropped {len(schemas)} session replica schemas.")

    tables = [
        "internal.change_history",
        "internal.generated_charts",
        "internal.generated_scripts",
        "internal.chat_messages",
        "internal.chat_sessions",
    ]
    for t in tables:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'internal' AND table_name = %s;",
            (t.split(".")[1],),
        )
        if cur.fetchone():
            cur.execute(f"TRUNCATE TABLE {t} CASCADE;")
    print("Truncated internal session tables.")

    cur.close()
    conn.close()

    charts_dir = Path("output/charts")
    if charts_dir.exists():
        for f in charts_dir.glob("*.json"):
            try:
                f.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    clear_all_sessions()
