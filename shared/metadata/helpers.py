import json
import logging
from typing import Any, Dict, Optional, Tuple

from shared.metadata.schema import TRACKED_METADATA_KEYS, truncate_words

logger = logging.getLogger(__name__)


def extract_tool_text(structured_data: Optional[Dict[str, Any]], raw_content: Any) -> str:
    """
    Extracts readable textual output or formatted JSON payload from a tool execution.

    Args:
        structured_data: Structured dictionary payload returned by the tool, if any.
        raw_content: Raw MCP content payload.

    Returns:
        str: Text representation of tool output.
    """
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
        sources: Tuple of dictionary outputs (e.g. result.metadata, result.structured_data).
        target_metadata: Mutable dictionary accumulating session metadata.
        last_dataset_id: ID of the most recent dataset prior to consolidation.
        last_exported_csv: File path of the most recent CSV prior to consolidation.

    Returns:
        Tuple[Optional[int], Optional[str]]: (updated_last_dataset_id, updated_last_exported_csv)
    """
    for source in sources:
        if not isinstance(source, dict):
            continue

        for key in TRACKED_METADATA_KEYS:
            val = source.get(key)
            if val is not None and val != "":
                target_metadata[key] = val
                if key == "dataset_id":
                    try:
                        last_dataset_id = int(val)
                    except (ValueError, TypeError):
                        pass

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
    or exported CSV paths from preceding steps.

    Args:
        tool_name: Name of the MCP tool to be invoked.
        raw_arguments: Original arguments defined in the plan step.
        active_metadata: Current active session metadata dictionary.
        session_id: Target session ID.
        last_dataset_id: ID of the most recently produced or active dataset.
        last_exported_csv: File path of the most recently exported CSV.

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

    # 3. Dynamic dataset_id resolution (placeholder or missing)
    if "dataset_id" in step_args:
        val = step_args.get("dataset_id")
        if (val is None or val == "" or str(val).lower() in {"0", "latest", "{{dataset_id}}"}) and last_dataset_id:
            step_args["dataset_id"] = last_dataset_id
    elif last_dataset_id and "dataset_id" not in step_args and tool_name in ("run_ml_analysis", "ml_analysis"):
        step_args["dataset_id"] = last_dataset_id

    # 4. Dynamic dataset_path resolution
    if "dataset_path" in step_args:
        val = str(step_args.get("dataset_path", "")).strip()
        if (not val or val.lower() in {"", "latest", "{{csv}}", "{{previous_step_csv}}", "{{file_path}}"}) and last_exported_csv:
            step_args["dataset_path"] = last_exported_csv

    # 5. Dynamic table_names injection
    if "table_names" not in step_args:
        tbls = active_meta.get("table_names")
        if tbls:
            step_args["table_names"] = tbls if isinstance(tbls, list) else [tbls]

    return step_args
