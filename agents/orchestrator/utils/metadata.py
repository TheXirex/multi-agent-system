"""
Orchestrator metadata adapter module.
Delegates to shared.metadata for centralized domain metadata handling across all agents.
"""
from typing import Any, Dict, Optional, Tuple

from agents.orchestrator.models.schemas import StepExecutionResult
from shared.metadata import (
    TRACKED_METADATA_KEYS,
    build_domain_metadata,
    consolidate_metadata,
    extract_tool_text,
    resolve_tool_arguments,
)


def extract_step_text(result: StepExecutionResult) -> str:
    """
    Extracts readable textual output from a StepExecutionResult.
    """
    return extract_tool_text(result.structured_data, result.raw_content)


def consolidate_step_metadata(
    result: StepExecutionResult,
    consolidated_metadata: Dict[str, Any],
    last_dataset_id: Optional[int] = None,
    last_exported_csv: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Consolidates domain metadata from StepExecutionResult into consolidated_metadata.
    """
    return consolidate_metadata(
        sources=(result.metadata, result.structured_data),
        target_metadata=consolidated_metadata,
        last_dataset_id=last_dataset_id,
        last_exported_csv=last_exported_csv,
    )


__all__ = [
    "TRACKED_METADATA_KEYS",
    "build_domain_metadata",
    "consolidate_metadata",
    "consolidate_step_metadata",
    "extract_step_text",
    "extract_tool_text",
    "resolve_tool_arguments",
]
