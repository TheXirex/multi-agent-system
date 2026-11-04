import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import Engine, text

from agents.db_agent.tools.base import BaseTool
from shared.db import apply_session_search_path, ensure_session_replica

logger = logging.getLogger(__name__)


class ExecuteSQLAndExportCSVTool(BaseTool):
    """
    Executes a SQL query against the active PostgreSQL database schema
    and returns execution metadata, column names, row count, and preview rows.
    """

    name: str = "execute_sql_to_csv"
    description: str = (
        "Executes a SQL query against the database and retrieves resulting records and summary metadata. "
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
                "description": "Optional descriptive title for the query result.",
            },
            "session_id": {
                "type": "string",
                "description": "Optional session ID to scope query execution to a session replica.",
            },
        },
        "required": ["query"],
    }

    def __init__(self, engine: Engine) -> None:
        """Initializes the SQL execution tool."""
        self.engine = engine

    def execute(
        self,
        query: str,
        filename: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Executes the provided SQL query against the target session schema and returns preview records.

        Args:
            query (str): SQL query statement to execute.
            filename (Optional[str]): Optional title for the resulting dataset.
            session_id (Optional[str]): Optional active session ID for replica routing.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            Dict[str, Any]: Execution result containing status, row_count, columns, and preview rows.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"query_result_{timestamp}"
        name = filename.removesuffix(".csv")

        try:
            if session_id:
                ensure_session_replica(self.engine, session_id)
            with self.engine.begin() as connection:
                apply_session_search_path(connection, session_id)
                result = connection.execute(text(query))
                columns: List[str] = list(result.keys()) if result.returns_rows else []
                fetched_rows = result.fetchall() if result.returns_rows else []

            row_count = len(fetched_rows)
            preview_rows: List[List[Any]] = [
                [
                    str(val) if val is not None and not isinstance(val, (int, float, bool, str)) else val
                    for val in row
                ]
                for row in fetched_rows[:5]
            ]

            formatted_rows: List[Dict[str, Any]] = [
                {
                    col: (
                        str(val)
                        if val is not None and not isinstance(val, (int, float, bool, str))
                        else val
                    )
                    for col, val in zip(columns, row)
                }
                for row in fetched_rows
            ]
            column_defs = [{"name": c, "label": c, "type": "string"} for c in columns]

            dataset_id: Optional[int] = None
            try:
                with self.engine.begin() as conn:
                    insert_res = conn.execute(
                        text(
                            """
                            INSERT INTO internal.generated_datasets (name, query, columns, rows, row_count, session_id)
                            VALUES (:name, :query, :columns, :rows, :row_count, :session_id)
                            RETURNING id
                            """
                        ),
                        {
                            "name": name,
                            "query": query,
                            "columns": json.dumps(column_defs),
                            "rows": json.dumps(formatted_rows),
                            "row_count": row_count,
                            "session_id": session_id,
                        },
                    )
                    dataset_id = insert_res.scalar()
            except Exception as save_err:
                logger.warning(f"Could not persist dataset to internal.generated_datasets: {save_err}")

            return {
                "status": "success",
                "dataset_id": dataset_id,
                "name": name,
                "file_name": f"{name}.csv",
                "row_count": row_count,
                "columns": columns,
                "preview": preview_rows,
            }
        except Exception as error:
            return {
                "status": "error",
                "error": str(error),
                "query": query,
            }
