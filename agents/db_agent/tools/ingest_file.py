import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from sqlalchemy import Engine, text

from agents.db_agent.tools.base import BaseTool

logger = logging.getLogger(__name__)


class IngestTabularFileTool(BaseTool):
    """
    Tool that ingests, validates, and stores tabular files (CSV, Excel) into PostgreSQL.
    Multi-sheet Excel files are partitioned into separate datasets.
    Handles corrupt, empty, or unsupported files gracefully and returns structured diagnostic errors.
    """

    name: str = "ingest_tabular_file"
    description: str = (
        "Ingests, validates, and records a tabular data file (CSV or Excel .xlsx/.xls) into the database. "
        "For Excel files with multiple sheets, each sheet is partitioned and stored as an individual dataset. "
        "Returns dataset IDs, column definitions, and summaries, or structured errors if the file is empty, missing, or corrupted."
    )
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the CSV or Excel file to ingest.",
            },
            "dataset_name": {
                "type": "string",
                "description": "Optional custom name for the ingested dataset.",
            },
            "session_id": {
                "type": "string",
                "description": "Optional session ID to bind this dataset exclusively to a chat session.",
            },
        },
        "required": ["file_path"],
    }

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def execute(
        self,
        file_path: Optional[str] = None,
        dataset_name: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingests and validates CSV or Excel data from disk path or bytes.

        Args:
            file_path (Optional[str]): Path to file on disk.
            dataset_name (Optional[str]): Custom dataset name.
            file_bytes (Optional[bytes]): Raw file bytes (for in-memory uploads).
            filename (Optional[str]): Explicit filename override.

        Returns:
            Dict[str, Any]: Structured result with status ('success' or 'error'),
                            dataset details or diagnostic error message.
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
                resolved_filename = dataset_name or "uploaded_data.csv"
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

        base_name = dataset_name or Path(resolved_filename).stem
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
                        sheet_items.append((f"{base_name} - {sname}", df_sheet))
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

        created_datasets: List[Dict[str, Any]] = []
        try:
            with self.engine.begin() as conn:
                for item_name, item_df in sheet_items:
                    item_df.columns = [str(c).strip() for c in item_df.columns]
                    columns_list = list(item_df.columns)
                    raw_records = item_df.to_dict(orient="records")

                    clean_records = [
                        {
                            col: (None if pd.isna(val) else val)
                            for col, val in row.items()
                        }
                        for row in raw_records
                    ]

                    res = conn.execute(
                        text("""
                            INSERT INTO internal.generated_datasets (name, file_name, file_path, query, row_count, columns, data, session_id)
                            VALUES (:name, :file_name, '', :query, :row_count, :columns, :data, :session_id)
                            RETURNING id
                        """),
                        {
                            "name": item_name,
                            "file_name": f"{item_name}.csv",
                            "query": f"-- Ingested dataset: {resolved_filename} ({item_name})",
                            "row_count": len(clean_records),
                            "columns": columns_list,
                            "data": json.dumps(clean_records, default=str),
                            "session_id": session_id,
                        },
                    )
                    ds_id = res.scalar()

                    types_summary = {col: str(item_df[col].dtype) for col in columns_list}
                    sample_preview = item_df.head(2).to_dict(orient="records")

                    created_datasets.append({
                        "id": ds_id,
                        "name": item_name,
                        "row_count": len(clean_records),
                        "columns": columns_list,
                        "column_types": types_summary,
                        "preview": sample_preview,
                        "session_id": session_id,
                    })

        except Exception as db_exc:
            logger.error(f"Database error storing datasets for '{resolved_filename}': {db_exc}", exc_info=True)
            return {
                "status": "error",
                "error": f"Database error storing datasets: {db_exc}",
                "metadata": {},
            }

        if not created_datasets:
            return {
                "status": "error",
                "error": f"No valid datasets could be extracted from '{resolved_filename}'.",
                "metadata": {},
            }

        primary_id = created_datasets[0]["id"]
        dataset_ids = [d["id"] for d in created_datasets]

        summary_lines = [
            f"File '{resolved_filename}' successfully ingested into database.",
        ]
        if len(created_datasets) == 1:
            ds = created_datasets[0]
            summary_lines.append(f"Created dataset #{ds['id']} ('{ds['name']}'): {ds['row_count']} rows, {len(ds['columns'])} columns.")
            summary_lines.append("Columns: " + ", ".join(f"`{c}`" for c in ds["columns"]))
        else:
            summary_lines.append(f"Partitioned into {len(created_datasets)} individual datasets:")
            for ds in created_datasets:
                summary_lines.append(f"- Dataset #{ds['id']} ('{ds['name']}'): {ds['row_count']} rows, columns: " + ", ".join(f"`{c}`" for c in ds["columns"]))

        return {
            "status": "success",
            "primary_dataset_id": primary_id,
            "dataset_ids": dataset_ids,
            "datasets": created_datasets,
            "session_id": session_id,
            "summary": "\n".join(summary_lines),
            "metadata": {
                "dataset_id": primary_id,
                "dataset_ids": dataset_ids,
                "session_id": session_id,
            },
        }
