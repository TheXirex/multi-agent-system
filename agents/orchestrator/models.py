from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """
    Metadata describing an MCP tool discovered from an MCP server.
    """

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    server_name: str = "db_agent"


class PlanStep(BaseModel):
    """
    Individual step in an orchestrated execution plan.
    """

    step_id: int
    tool_name: str
    description: str = ""
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    """
    Structured execution plan produced by the Planner agent.
    """

    thought: str = ""
    steps: List[PlanStep] = Field(default_factory=list)


class StepExecutionResult(BaseModel):
    """
    Result of an individual tool call executed by the Executor via MCP.
    """

    step_id: int
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    raw_content: Any = None
    structured_data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None


class RawExecutionAnswer(BaseModel):
    """
    Consolidated raw execution outputs and metadata passed from Executor to Finalizer.
    """

    steps: List[StepExecutionResult] = Field(default_factory=list)
    raw_text: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FinalOrchestratorResult(BaseModel):
    """
    Final synthesized result returned by the Orchestrator to the UI / caller.
    """

    user_query: str
    plan: ExecutionPlan
    raw_answer: RawExecutionAnswer
    final_response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts result into a serializable dictionary matching UI expectations.
        """
        return {
            "user_query": self.user_query,
            "response": self.final_response,
            "metadata": self.metadata,
            "plan": self.plan.model_dump(),
            "raw_answer": self.raw_answer.model_dump(),
        }
