"""
Guardrail utilities for the Orchestrator Agent.
Enforces domain boundary policies and handles out-of-scope query refusals.
"""
import logging
from typing import Any, Dict

from agents.orchestrator.models.state import OrchestratorState

logger = logging.getLogger(__name__)

DEFAULT_REFUSAL_MESSAGE = (
    "I am a specialized assistant designed for database querying, "
    "data exploration, analytics, and machine learning. "
    "I cannot assist with off-topic requests such as cooking recipes or general chit-chat. "
    "Please let me know if you would like help analyzing your data!"
)


def is_in_scope(state: OrchestratorState) -> bool:
    """
    Evaluates whether the user request state is within the allowed domain scope.

    Args:
        state (OrchestratorState): The current Orchestrator graph state.

    Returns:
        bool: True if request is in-scope, False otherwise.
    """
    return bool(state.get("is_in_scope", True))


def create_guardrail_refusal_response(state: OrchestratorState) -> Dict[str, Any]:
    """
    Constructs a deterministic refusal response dictionary for out-of-scope queries.
    Prevents any tool execution and registers guardrail metadata.

    Args:
        state (OrchestratorState): The current Orchestrator graph state.

    Returns:
        Dict[str, Any]: State update payload with refusal response and metadata.
    """
    direct_text = (state.get("direct_response") or "").strip()
    rejection_reason = state.get("rejection_reason") or "Request is out of scope"
    user_query = state.get("user_query", "")

    logger.info(f"Guardrail triggered for query '{user_query[:50]}...'. Reason: {rejection_reason}")

    if not direct_text:
        direct_text = DEFAULT_REFUSAL_MESSAGE

    merged_metadata = dict(state.get("metadata") or {})
    merged_metadata["guardrail_triggered"] = True
    merged_metadata["rejection_reason"] = rejection_reason

    return {
        "final_response": direct_text,
        "raw_text": "",
        "metadata": merged_metadata,
        "execution_results": [],
    }
