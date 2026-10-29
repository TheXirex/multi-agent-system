import json
import logging
from typing import Any, Dict, Optional, Tuple

from shared.metadata.schema import TRACKED_METADATA_KEYS

logger = logging.getLogger(__name__)


def _parse_positive_int(val: Any) -> Optional[int]:
    """Parses a positive integer ID from an integer or digit string value, ignoring booleans."""
    if isinstance(val, int) and not isinstance(val, bool) and val > 0:
        return val
    if isinstance(val, str) and val.strip().isdigit():
        parsed = int(val.strip())
        return parsed if parsed > 0 else None
    return None


def extract_tool_text(structured_data: Optional[Dict[str, Any]], raw_content: Any) -> str:
    """Extracts readable textual output or formatted JSON payload from a tool execution."""
    if structured_data and isinstance(structured_data, dict):
        resp_text = structured_data.get("response") or structured_data.get("schema")
        if resp_text:
            return str(resp_text)
        return json.dumps(structured_data, indent=2, default=str)
    if raw_content:
        return str(raw_content)
    return ""


def consolidate_metadata(
    sources: Tuple[Any, ...],
    target_metadata: Dict[str, Any],
    last_dataset_id: Optional[int] = None,
    last_exported_csv: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Extracts and updates tracked metadata across dictionary sources (e.g. metadata and structured_data).

    Args:
        sources (Tuple[Any, ...]): Tuple of dictionary outputs (e.g. result.metadata, result.structured_data).
        target_metadata (Dict[str, Any]): Mutable dictionary accumulating session metadata.
        last_dataset_id (Optional[int]): ID of the most recent dataset prior to consolidation.
        last_exported_csv (Optional[str]): File path of the most recent dataset prior to consolidation.

    Returns:
        Tuple[Optional[int], Optional[str]]: Updated (last_dataset_id, last_exported_csv) tuple.
    """
    for source in sources:
        if not isinstance(source, dict):
            continue

        for key in TRACKED_METADATA_KEYS:
            val = source.get(key)
            if val is not None and val != "":
                target_metadata[key] = val
                if key == "dataset_id":
                    parsed_id = _parse_positive_int(val)
                    if parsed_id is not None:
                        last_dataset_id = parsed_id

        # Preserve and assign SQL / Python script IDs specifically
        if source.get("sql_query"):
            target_metadata["sql_query"] = source["sql_query"]
        if source.get("sql_script_id"):
            target_metadata["sql_script_id"] = source["sql_script_id"]
        elif not source.get("code") and (source.get("sql_description") or source.get("sql_query")) and source.get("script_id") is not None:
            target_metadata["sql_script_id"] = source["script_id"]

        if source.get("python_script_id"):
            target_metadata["python_script_id"] = source["python_script_id"]
        elif source.get("code") and source.get("script_id") is not None:
            target_metadata["python_script_id"] = source["script_id"]

        # Normalize and guarantee table_names presence
        t_names = source.get("table_names")
        if t_names:
            if isinstance(t_names, list):
                target_metadata["table_names"] = [str(x) for x in t_names if x]
            elif isinstance(t_names, str):
                target_metadata["table_names"] = [t_names]
        elif "table_name" in source and source.get("table_name"):
            t_name = str(source["table_name"]).strip()
            if t_name and "table_names" not in target_metadata:
                target_metadata["table_names"] = [t_name]

        # Normalize and guarantee chart_ids presence
        c_ids = source.get("chart_ids")
        if c_ids:
            if isinstance(c_ids, list):
                target_metadata["chart_ids"] = [int(x) for x in c_ids if x is not None]
                if "chart_id" not in target_metadata and target_metadata["chart_ids"]:
                    target_metadata["chart_id"] = target_metadata["chart_ids"][0]
            elif isinstance(c_ids, int):
                target_metadata["chart_ids"] = [c_ids]
                target_metadata["chart_id"] = c_ids
        elif source.get("chart_id") is not None:
            cid = int(source["chart_id"])
            target_metadata["chart_id"] = cid
            if "chart_ids" not in target_metadata:
                target_metadata["chart_ids"] = [cid]

        file_path = source.get("file_path")
        if file_path:
            last_exported_csv = str(file_path).strip()

    return last_dataset_id, last_exported_csv


def resolve_tool_arguments(
    tool_name: str,
    raw_arguments: Optional[Dict[str, Any]],
    active_metadata: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    last_dataset_id: Optional[int] = None,
    last_exported_csv: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolves dynamic step arguments by injecting session context, active dataset IDs,
    or table names from preceding steps.

    Args:
        tool_name (str): Name of the MCP tool to be invoked.
        raw_arguments (Optional[Dict[str, Any]]): Original arguments defined in the plan step.
        active_metadata (Optional[Dict[str, Any]]): Current active session metadata dictionary.
        session_id (Optional[str]): Target session ID.
        last_dataset_id (Optional[int]): ID of the most recently produced or active dataset.
        last_exported_csv (Optional[str]): File path of the most recently exported dataset.

    Returns:
        Dict[str, Any]: Fully resolved arguments dictionary ready for tool execution.
    """
    step_args = dict(raw_arguments or {})
    active_meta = dict(active_metadata or {})

    # 1. Inject session_id if absent
    effective_session_id = session_id or active_meta.get("session_id")
    if effective_session_id and "session_id" not in step_args:
        step_args["session_id"] = effective_session_id

    # 2. Inject dataset_ids for ML analysis if available in session
    if "dataset_ids" not in step_args and active_meta.get("dataset_ids") and tool_name in ("run_ml_analysis", "ml_analysis"):
        step_args["dataset_ids"] = active_meta["dataset_ids"]
    elif "dataset_ids" in step_args:
        raw_ids = step_args.get("dataset_ids")
        if isinstance(raw_ids, list):
            clean_ids = [parsed for x in raw_ids if (parsed := _parse_positive_int(x)) is not None]
            if clean_ids:
                step_args["dataset_ids"] = clean_ids
            else:
                step_args.pop("dataset_ids", None)
        else:
            step_args.pop("dataset_ids", None)

    # 3. Dynamic dataset_id resolution (placeholder or missing)
    if "dataset_id" in step_args:
        parsed_id = _parse_positive_int(step_args.get("dataset_id"))
        if parsed_id is not None:
            step_args["dataset_id"] = parsed_id
        elif last_dataset_id:
            step_args["dataset_id"] = int(last_dataset_id)
        else:
            step_args.pop("dataset_id", None)
    elif last_dataset_id and "dataset_id" not in step_args and tool_name in ("run_ml_analysis", "ml_analysis"):
        step_args["dataset_id"] = int(last_dataset_id)

    # 4. Dynamic dataset_path resolution
    if "dataset_path" in step_args:
        val = str(step_args.get("dataset_path", "")).strip()
        if not val or val.lower() in {"", "latest", "{{csv}}", "{{previous_step_csv}}", "{{file_path}}", "none", "null"}:
            if last_exported_csv:
                step_args["dataset_path"] = last_exported_csv
            else:
                step_args.pop("dataset_path", None)

    # 5. Dynamic table_names injection and normalization
    for alias in ("table", "tables", "table_name"):
        if alias in step_args and "table_names" not in step_args:
            tn = step_args.pop(alias)
            if tn:
                step_args["table_names"] = [tn] if isinstance(tn, str) else list(tn)

    if "table_names" in step_args:
        if isinstance(step_args["table_names"], str):
            step_args["table_names"] = [step_args["table_names"]]
    else:
        task_desc = (
            str(step_args.get("task_description") or "")
            + " "
            + str(step_args.get("instruction") or "")
            + " "
            + str(step_args.get("user_input") or "")
        ).lower()
        desc_words = set("".join(c if c.isalnum() else " " for c in task_desc).split())
        known_tables = ["product_reviews", "products", "orders", "categories", "users"]
        detected_tables = []
        for t in known_tables:
            singular = t[:-1] if t.endswith("s") else t
            if t in desc_words or singular in desc_words or (t == "product_reviews" and "reviews" in desc_words):
                if t == "products" and "product_reviews" in detected_tables:
                    continue
                detected_tables.append(t)

        if detected_tables:
            step_args["table_names"] = detected_tables
        else:
            tbls = active_meta.get("table_names")
            if tbls:
                step_args["table_names"] = tbls if isinstance(tbls, list) else [tbls]

    # 6. Dynamic sql_query injection if available in session
    if "sql_query" not in step_args and active_meta.get("sql_query") and tool_name in ("run_ml_analysis", "ml_analysis"):
        meta_tables = active_meta.get("table_names")
        meta_set = set(meta_tables if isinstance(meta_tables, list) else [meta_tables]) if meta_tables else set()
        curr_tables = step_args.get("table_names") or []
        curr_set = set(curr_tables if isinstance(curr_tables, list) else [curr_tables])
        if not curr_set or curr_set == meta_set:
            step_args["sql_query"] = active_meta["sql_query"]

    return step_args
