import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from sqlalchemy import Engine, text

from agents.db_agent.tools.base import BaseTool
from shared.db import ensure_session_replica, get_session_schema_or_public

logger = logging.getLogger(__name__)


def sanitize_table_name(name: str) -> str:
    """
    Sanitizes a file or sheet name into a clean, valid PostgreSQL table identifier.
    """
    clean = "".join(c if c.isalnum() else "_" for c in str(name).lower().strip())
    clean = "_".join(p for p in clean.split("_") if p)
    if not clean:
        clean = "uploaded_table"
    elif clean[0].isdigit():
        clean = f"table_{clean}"
    return clean[:63]


def sanitize_column_name(col: str) -> str:
    """
    Sanitizes a column header into a valid, safe PostgreSQL column identifier.
    """
    clean = "".join(c if c.isalnum() else "_" for c in str(col).lower().strip())
    clean = "_".join(p for p in clean.split("_") if p)
    if not clean:
        clean = "col"
    elif clean[0].isdigit():
        clean = f"c_{clean}"
    return clean[:63]


class IngestTabularFileTool(BaseTool):
    """
    Tool that ingests tabular files (CSV, Excel) directly into isolated PostgreSQL tables
    inside the session schema replica. If a table name already exists or collides, asks the user
    for clarification instead of guessing.
    """

    name: str = "ingest_tabular_file"
    description: str = (
        "Ingests a tabular file (CSV or Excel .xlsx/.xls) and creates dedicated relational database table(s) "
        "inside the active session replica. If the table already exists, pauses and asks the user for clarification."
    )
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the CSV or Excel file to ingest.",
            },
            "table_name": {
                "type": "string",
                "description": "Optional custom name for the resulting database table.",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Set to True if user explicitly confirmed overwriting an existing table.",
            },
            "session_id": {
                "type": "string",
                "description": "Optional session ID to scope table creation to the session replica.",
            },
        },
    }

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def execute(
        self,
        file_path: Optional[str] = None,
        table_name: Optional[str] = None,
        dataset_name: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        overwrite: bool = False,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Parses CSV/Excel and creates relational tables in session schema.
        """
        resolved_filename = filename
        source_buffer: Optional[Union[Path, io.BytesIO]] = None

        if file_bytes is not None:
            if len(file_bytes) == 0:
                return {
                    "status": "error",
                    "error": "The provided file is empty (0 bytes). Cannot ingest empty file.",
                    "metadata": {},
                }
            source_buffer = io.BytesIO(file_bytes)
            if not resolved_filename:
                resolved_filename = table_name or dataset_name or "uploaded_data.csv"
        elif file_path:
            path_obj = Path(file_path)
            if not path_obj.exists():
                return {
                    "status": "error",
                    "error": f"File '{file_path}' does not exist.",
                    "metadata": {},
                }
            if not path_obj.is_file():
                return {
                    "status": "error",
                    "error": f"Path '{file_path}' is not a regular file.",
                    "metadata": {},
                }
            if path_obj.stat().st_size == 0:
                return {
                    "status": "error",
                    "error": f"File '{file_path}' is empty (0 bytes). Cannot ingest empty file.",
                    "metadata": {},
                }
            source_buffer = path_obj
            if not resolved_filename:
                resolved_filename = path_obj.name
        else:
            return {
                "status": "error",
                "error": "Neither 'file_path' nor 'file_bytes' was provided.",
                "metadata": {},
            }

        ext = Path(resolved_filename).suffix.lower()
        if ext not in (".csv", ".xlsx", ".xls"):
            return {
                "status": "error",
                "error": f"Unsupported file extension '{ext}'. Supported formats: .csv, .xlsx, .xls.",
                "metadata": {},
            }

        base_name = table_name or dataset_name or Path(resolved_filename).stem
        sheet_items: List[Tuple[str, pd.DataFrame]] = []

        try:
            if ext == ".csv":
                try:
                    df = pd.read_csv(source_buffer)
                except pd.errors.EmptyDataError:
                    return {
                        "status": "error",
                        "error": f"CSV file '{resolved_filename}' contains no headers or readable data.",
                        "metadata": {},
                    }
                except Exception as csv_err:
                    logger.warning(f"Failed to parse CSV file '{resolved_filename}': {csv_err}")
                    return {
                        "status": "error",
                        "error": f"Failed to parse CSV file '{resolved_filename}'. Please ensure the file has a valid format with readable rows and columns.",
                        "metadata": {},
                    }

                if df.empty and len(df.columns) == 0:
                    return {
                        "status": "error",
                        "error": f"CSV file '{resolved_filename}' contains no readable columns or rows.",
                        "metadata": {},
                    }
                sheet_items.append((base_name, df))

            else:  # .xlsx or .xls
                try:
                    excel = pd.ExcelFile(source_buffer, engine="openpyxl" if ext == ".xlsx" else None)
                except Exception as xl_err:
                    logger.warning(f"Failed to read Excel file '{resolved_filename}': {xl_err}")
                    return {
                        "status": "error",
                        "error": f"Failed to read Excel file '{resolved_filename}'. The file appears to be corrupted, incomplete, or not a valid Excel spreadsheet.",
                        "metadata": {},
                    }

                if not excel.sheet_names:
                    return {
                        "status": "error",
                        "error": f"Excel workbook '{resolved_filename}' contains no sheets.",
                        "metadata": {},
                    }

                for sname in excel.sheet_names:
                    try:
                        df_sheet = pd.read_excel(excel, sheet_name=sname)
                        sheet_items.append((f"{base_name}_{sname}", df_sheet))
                    except Exception as sheet_err:
                        logger.warning(f"Error reading sheet '{sname}' in '{resolved_filename}': {sheet_err}")

                if not sheet_items:
                    return {
                        "status": "error",
                        "error": f"Excel workbook '{resolved_filename}' contains no readable sheets.",
                        "metadata": {},
                    }

        except Exception as parse_exc:
            return {
                "status": "error",
                "error": f"Error parsing tabular data from '{resolved_filename}': {parse_exc}",
                "metadata": {},
            }

        # 1. Resolve target schema
        target_schema = ensure_session_replica(self.engine, session_id) if session_id else "public"

        # 2. Check for table name collisions
        with self.engine.connect() as conn:
            existing_tables = set(
                r[0].lower()
                for r in conn.execute(
                    text("""
                        SELECT table_name FROM information_schema.tables 
                        WHERE table_schema = :s AND table_type = 'BASE TABLE'
                    """),
                    {"s": target_schema},
                ).fetchall()
            )

        # Check each target item
        for item_name, _ in sheet_items:
            candidate_table = sanitize_table_name(item_name)
            if candidate_table in existing_tables and not overwrite:
                alt_name = f"{candidate_table}_v2"
                questions = [
                    f"Table '{candidate_table}' already exists in your session database. How would you like to proceed?\n"
                    f"1. Overwrite the existing table '{candidate_table}'.\n"
                    f"2. Save as a new table named '{alt_name}'.\n"
                    f"3. Provide a custom table name."
                ]
                clarification_msg = (
                    f"⚠️ Table `{candidate_table}` already exists in your session database.\n\n"
                    f"Please specify how you would like to proceed: overwrite it, save under a new name (e.g. `{alt_name}`), or choose a custom name?"
                )
                return {
                    "status": "clarification_needed",
                    "questions": questions,
                    "response": clarification_msg,
                    "metadata": {
                        "status": "clarification_needed",
                        "questions": questions,
                        "conflicting_table": candidate_table,
                        "session_id": session_id,
                    },
                }

        # 3. Create real PostgreSQL tables
        created_tables: List[Dict[str, Any]] = []

        try:
            with self.engine.begin() as conn:
                for item_name, item_df in sheet_items:
                    target_table = sanitize_table_name(item_name)

                    # Sanitize column names
                    used_cols: set = set()
                    new_cols: List[str] = []
                    for c in item_df.columns:
                        sc = sanitize_column_name(c)
                        orig = sc
                        counter = 1
                        while sc in used_cols:
                            sc = f"{orig}_{counter}"
                            counter += 1
                        used_cols.add(sc)
                        new_cols.append(sc)

                    clean_df = item_df.copy()
                    clean_df.columns = new_cols

                    # Write directly to session schema table
                    clean_df.to_sql(
                        name=target_table,
                        con=conn,
                        schema=target_schema,
                        if_exists="replace",
                        index=False,
                    )

                    # Record change in change_history for full rollback support
                    if session_id:
                        conn.execute(
                            text("""
                                INSERT INTO internal.change_history (
                                    session_id, action_type, table_name, description,
                                    executed_sql, rollback_sql, before_state, after_state
                                ) VALUES (
                                    :session_id, 'CREATE_TABLE', :table_name, :description,
                                    :executed_sql, :rollback_sql, '[]', '[]'
                                )
                            """),
                            {
                                "session_id": session_id,
                                "table_name": target_table,
                                "description": f"Ingested {resolved_filename} as table '{target_table}'",
                                "executed_sql": f"-- Created table {target_table} from {resolved_filename}",
                                "rollback_sql": f'DROP TABLE IF EXISTS "{target_table}" CASCADE;',
                            },
                        )

                    preview_records = clean_df.head(5).to_dict(orient="records")
                    created_tables.append({
                        "table_name": target_table,
                        "row_count": len(clean_df),
                        "columns": new_cols,
                        "preview": preview_records,
                    })

        except Exception as db_exc:
            logger.error(f"Database error writing tables for '{resolved_filename}': {db_exc}", exc_info=True)
            return {
                "status": "error",
                "error": f"Database error creating table: {db_exc}",
                "metadata": {},
            }

        if not created_tables:
            return {
                "status": "error",
                "error": f"No valid tables could be created from '{resolved_filename}'.",
                "metadata": {},
            }

        primary_table = created_tables[0]["table_name"]
        all_table_names = [t["table_name"] for t in created_tables]

        # Generate readable summary
        msg_lines = [
            f"📁 **File successfully uploaded and stored as a database table:** `{primary_table}`\n",
        ]
        if len(created_tables) == 1:
            t = created_tables[0]
            msg_lines.append(f"Created table **`{t['table_name']}`**: {t['row_count']} rows, {len(t['columns'])} columns.")
            msg_lines.append("\n**Columns:** " + ", ".join(f"`{c}`" for c in t["columns"]))
        else:
            msg_lines.append(f"Partitioned into **{len(created_tables)} individual tables** (by sheet):")
            for t in created_tables:
                msg_lines.append(f"- **`{t['table_name']}`**: {t['row_count']} rows, columns: " + ", ".join(f"`{c}`" for c in t["columns"]))

        msg_lines.append("\nYou can now execute SQL queries against this table or train machine learning models.")
        msg_markdown = "\n".join(msg_lines)

        return {
            "status": "success",
            "table_name": primary_table,
            "table_names": all_table_names,
            "tables": created_tables,
            "session_id": session_id,
            "response": msg_markdown,
            "summary": msg_markdown,
            "metadata": {
                "table_name": primary_table,
                "table_names": all_table_names,
                "session_id": session_id,
            },
        }
