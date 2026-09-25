import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import Engine, text

from agents.db_agent.tools.base import BaseTool


class ExecuteSQLAndExportCSVTool(BaseTool):
    """
    Executes an SQL query against the database and exports the resulting rows to a CSV file.
    """

    name: str = "execute_sql_to_csv"
    description: str = (
        "Executes a SQL query against the database and saves the result rows into a CSV file. "
        "Use this tool when you need to run queries and export data for user inspection or analysis."
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
                "description": "Optional custom filename for the output CSV file (without or with .csv extension).",
            },
        },
        "required": ["query"],
    }

    def __init__(self, engine: Engine, output_dir: Path) -> None:
        self.engine = engine
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, query: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes the provided SQL query and exports the dataset to a CSV file.

        Args:
            query (str): SQL query statement to be executed.
            filename (Optional[str]): Optional custom file name for the target CSV file.

        Returns:
            Dict[str, Any]: Execution details including file path, row count, and column headers.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"query_result_{timestamp}.csv"
        elif not filename.endswith(".csv"):
            filename = f"{filename}.csv"

        target_path = self.output_dir / filename

        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(query))
                columns = list(result.keys())
                rows: List[List[Any]] = [list(row) for row in result.fetchall()]

            with open(target_path, mode="w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(columns)
                writer.writerows(rows)

            preview_rows = [
                [str(val) if val is not None and not isinstance(val, (int, float, bool, str)) else val for val in row]
                for row in rows[:5]
            ]

            return {
                "status": "success",
                "file_path": str(target_path.resolve()),
                "file_name": target_path.name,
                "row_count": len(rows),
                "columns": columns,
                "preview": preview_rows,
            }
        except Exception as error:
            return {
                "status": "error",
                "error": str(error),
                "query": query,
            }
