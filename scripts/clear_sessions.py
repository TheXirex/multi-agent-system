import psycopg2
import os
import shutil
from pathlib import Path

def clear_all_sessions():
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/app_db")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'session_%';")
    schemas = [r[0] for r in cur.fetchall()]
    for s in schemas:
        cur.execute(f'DROP SCHEMA IF EXISTS "{s}" CASCADE;')
    print(f"Dropped {len(schemas)} session schemas.")

    tables = [
        "internal.change_history",
        "internal.generated_charts",
        "internal.generated_scripts",
        "internal.chat_messages",
        "internal.chat_sessions",
    ]
    for t in tables:
        cur.execute(f"TRUNCATE TABLE {t} CASCADE;")
    print("Truncated internal session tables.")

    cur.close()
    conn.close()

    # Clean output charts directory
    charts_dir = Path("output/charts")
    if charts_dir.exists():
        for f in charts_dir.glob("*.json"):
            try:
                f.unlink()
            except Exception:
                pass
        print(f"Cleared charts in {charts_dir}")

    showcase_html = Path("output/charts_showcase.html")
    if showcase_html.exists():
        showcase_html.unlink()
        print("Removed charts_showcase.html")

if __name__ == "__main__":
    clear_all_sessions()
