import csv
from datetime import datetime
import json
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
from sqlalchemy import Engine, text

from agents.db_agent.tools.base import BaseTool
from shared.db import apply_session_search_path, ensure_session_replica


class ExecuteSQLAndExportCSVTool(BaseTool):
    """
    Executes an SQL query against the database, records the dataset in PostgreSQL,
    and returns its dataset ID.
    """

    name: str = "execute_sql_to_csv"
    description: str = (
        "Executes a SQL query against the database and saves the result dataset into the database. "
        "Use this tool when you need to run queries and retrieve data for analysis or display."
    )
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Valid SQL query to execute against the database.",
            },
            "filename": {
                "type": "string",
                "description": "Optional name for the dataset.",
            },
            "session_id": {
                "type": "string",
                "description": "Optional session ID to scope query and dataset to a session replica.",
            },
        },
        "required": ["query"],
    }

    def __init__(self, engine: Engine, output_dir: Optional[Path] = None) -> None:
        self.engine = engine
        self.output_dir = output_dir or (Path(tempfile.gettempdir()) / "app_temp")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        query: str,
        filename: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Executes the provided SQL query and returns the resulting records.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"query_result_{timestamp}"
        name = filename.removesuffix(".csv")

        try:
            schema_name = ensure_session_replica(self.engine, session_id) if session_id else None
            with self.engine.begin() as connection:
                apply_session_search_path(connection, session_id)
                result = connection.execute(text(query))
                columns = list(result.keys()) if result.returns_rows else []
                raw_rows: List[List[Any]] = [list(row) for row in result.fetchall()] if result.returns_rows else []

            preview_rows = [
                [str(val) if val is not None and not isinstance(val, (int, float, bool, str)) else val for val in row]
                for row in raw_rows[:5]
            ]

            return {
                "status": "success",
                "name": name,
                "file_name": f"{name}.csv",
                "row_count": len(raw_rows),
                "columns": columns,
                "preview": preview_rows,
            }
        except Exception as error:
            return {
                "status": "error",
                "error": str(error),
                "query": query,
            }
