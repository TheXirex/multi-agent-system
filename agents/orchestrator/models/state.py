from typing import Any, Dict, List, Optional, TypedDict
from agents.orchestrator.models.schemas import PlanStep, StepExecutionResult, ToolDefinition


class OrchestratorState(TypedDict):
    """
    LangGraph state schema for Orchestrator agent workflow.
    """

    user_query: str
    tools: List[ToolDefinition]
    requires_tools: bool
    direct_response: str
    thought: str
    steps: List[PlanStep]
    execution_results: List[StepExecutionResult]
    raw_text: str
    metadata: Dict[str, Any]
    final_response: str
    error: Optional[str]
