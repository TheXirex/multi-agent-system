from typing import Any, Dict, List, Optional, Tuple

# Universal domain metadata keys propagated across orchestrator, domain agents, and backend
TRACKED_METADATA_KEYS: Tuple[str, ...] = (
    "dataset_id",
    "dataset_ids",
    "chart_id",
    "chart_ids",
    "script_id",
    "sql_script_id",
    "python_script_id",
    "sql_query",
    "table_name",
    "table_names",
    "sql_description",
    "code",
    "code_title",
    "task_description",
    "status",
    "questions",
    "guardrail_triggered",
    "rejection_reason",
    "session_id",
    "change_id",
)


def truncate_words(text: Optional[str], max_words: int = 5) -> str:
    """Truncates a title or description string to at most max_words, stripping HTML tags and trailing punctuation."""
    if not text:
        return ""
    cleaned = str(text).strip().strip("\"' \t\r\n")
    while "<" in cleaned and ">" in cleaned:
        start = cleaned.find("<")
        end = cleaned.find(">", start)
        if end != -1:
            cleaned = (cleaned[:start] + cleaned[end + 1 :]).strip()
        else:
            break
    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned.rstrip(" ,;:-–—.")
    truncated = " ".join(words[:max_words]).strip()
    return truncated.rstrip(" ,;:-–—.")


def build_domain_metadata(
    *,
    dataset_id: Optional[int] = None,
    dataset_ids: Optional[List[int]] = None,
    chart_id: Optional[int] = None,
    chart_ids: Optional[List[int]] = None,
    script_id: Optional[int] = None,
    sql_script_id: Optional[int] = None,
    python_script_id: Optional[int] = None,
    sql_query: Optional[str] = None,
    code: Optional[str] = None,
    code_title: Optional[str] = None,
    task_description: Optional[str] = None,
    table_name: Optional[str] = None,
    table_names: Optional[Any] = None,
    sql_description: Optional[str] = None,
    status: Optional[str] = None,
    questions: Optional[List[Any]] = None,
    guardrail_triggered: Optional[bool] = None,
    rejection_reason: Optional[str] = None,
    session_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Constructs a clean, normalized domain metadata dictionary with non-empty values.
    Enforces concise titles (4-5 words max) on code_title, task_description, table_name, and sql_description.

    Args:
        dataset_id (Optional[int]): Primary dataset ID.
        dataset_ids (Optional[List[int]]): List of dataset IDs if multiple exist.
        chart_id (Optional[int]): Primary chart ID.
        chart_ids (Optional[List[int]]): List of chart IDs if multiple exist.
        script_id (Optional[int]): Saved ML/SQL script ID.
        sql_script_id (Optional[int]): Saved SQL script ID.
        python_script_id (Optional[int]): Saved Python script ID.
        sql_query (Optional[str]): Executed SQL query string.
        code (Optional[str]): Executed Python code snippet.
        code_title (Optional[str]): Concise descriptive title for Python script (4-5 words max).
        task_description (Optional[str]): Concise task description or script title (4-5 words max).
        table_name (Optional[str]): Primary table title or identifier (4-5 words max).
        table_names (Optional[Any]): List of table names or single table name string.
        sql_description (Optional[str]): Concise SQL description (4-5 words max).
        status (Optional[str]): Flow status indicator (e.g. 'clarification_needed', 'completed').
        questions (Optional[List[Any]]): Clarification questions list when status is 'clarification_needed'.
        guardrail_triggered (Optional[bool]): Whether query was blocked by safety/domain guardrails.
        rejection_reason (Optional[str]): Human-readable explanation of guardrail refusal.
        session_id (Optional[str]): Active session UUID.
        extra (Optional[Dict[str, Any]]): Additional arbitrary key-value pairs to include if non-empty.

    Returns:
        Dict[str, Any]: Consolidated metadata dictionary.
    """
    meta: Dict[str, Any] = {}

    if dataset_id is not None:
        meta["dataset_id"] = dataset_id

    if dataset_ids:
        meta["dataset_ids"] = dataset_ids
        if "dataset_id" not in meta and dataset_ids:
            meta["dataset_id"] = dataset_ids[0]

    if chart_id is not None:
        meta["chart_id"] = chart_id

    if chart_ids:
        meta["chart_ids"] = chart_ids
        if "chart_id" not in meta and chart_ids:
            meta["chart_id"] = chart_ids[0]

    if script_id is not None:
        meta["script_id"] = script_id

    if sql_script_id is not None:
        meta["sql_script_id"] = sql_script_id

    if python_script_id is not None:
        meta["python_script_id"] = python_script_id

    if sql_query:
        meta["sql_query"] = sql_query

    if code:
        meta["code"] = code

    if code_title:
        meta["code_title"] = truncate_words(code_title, 5)

    if task_description:
        meta["task_description"] = truncate_words(task_description, 5)

    if table_name:
        meta["table_name"] = truncate_words(table_name, 5)

    if table_names:
        if isinstance(table_names, str):
            meta["table_names"] = [table_names]
        elif isinstance(table_names, list):
            meta["table_names"] = [str(t) for t in table_names if t]
    elif table_name:
        meta["table_names"] = [str(table_name)]

    if sql_description:
        meta["sql_description"] = truncate_words(sql_description, 5)

    if status:
        meta["status"] = status

    if questions:
        meta["questions"] = questions

    if guardrail_triggered is not None:
        meta["guardrail_triggered"] = guardrail_triggered

    if rejection_reason:
        meta["rejection_reason"] = rejection_reason

    if session_id:
        meta["session_id"] = session_id

    if extra:
        for k, v in extra.items():
            if v is not None and v != "":
                meta[k] = v

    return meta
