"""
Domain metadata constants, schemas, and builders across all agents and services.
"""
from typing import Any, Dict, List, Optional, Tuple

# Universal domain metadata keys propagated across orchestrator, domain agents, and backend
TRACKED_METADATA_KEYS: Tuple[str, ...] = (
    "dataset_id",
    "dataset_ids",
    "chart_id",
    "chart_ids",
    "script_id",
    "code",
    "status",
    "questions",
    "guardrail_triggered",
    "rejection_reason",
    "session_id",
)


def build_domain_metadata(
    *,
    dataset_id: Optional[int] = None,
    dataset_ids: Optional[List[int]] = None,
    chart_id: Optional[int] = None,
    chart_ids: Optional[List[int]] = None,
    script_id: Optional[int] = None,
    code: Optional[str] = None,
    status: Optional[str] = None,
    questions: Optional[List[str]] = None,
    guardrail_triggered: Optional[bool] = None,
    rejection_reason: Optional[str] = None,
    session_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Constructs a clean, normalized domain metadata dictionary with non-empty values.

    Args:
        dataset_id: Primary dataset ID.
        dataset_ids: List of dataset IDs if multiple exist.
        chart_id: Primary chart ID.
        chart_ids: List of chart IDs if multiple exist.
        script_id: Saved ML/SQL script ID.
        code: Executed Python code snippet.
        status: Flow status indicator (e.g. 'clarification_needed', 'completed').
        questions: Clarification questions list when status is 'clarification_needed'.
        guardrail_triggered: Whether query was blocked by safety/domain guardrails.
        rejection_reason: Human-readable explanation of guardrail refusal.
        session_id: Active session UUID.
        extra: Additional arbitrary key-value pairs to include if non-empty.

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

    if code:
        meta["code"] = code

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
