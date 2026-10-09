from typing import Any, Dict, List, Optional
from pydantic import AliasChoices, BaseModel, Field


class ToolDefinition(BaseModel):
    """
    Metadata describing an MCP tool discovered from an MCP server.
    """

    name: str = Field(description="Unique tool identifier name")
    description: str = Field(default="", description="Human-readable description of what the tool does")
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON schema defining input arguments")
    server_name: str = Field(default="db_agent", description="Identifier of the MCP server providing this tool")


class PlanStep(BaseModel):
    """
    Individual step in an orchestrated execution plan.
    """

    step_id: int = Field(default=1, description="Sequential index of the execution step")
    tool_name: str = Field(
        default="",
        validation_alias=AliasChoices("tool_name", "tool", "name"),
        description="Name of the MCP tool to invoke",
    )
    description: str = Field(default="", description="Short description of the step purpose")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments dictionary for the tool invocation")


class ExecutionPlan(BaseModel):
    """
    Structured execution plan produced by the Orchestrator routing and planning step.
    """

    requires_tools: bool = Field(default=True, description="Whether domain tools must be executed")
    direct_response: str = Field(default="", description="Direct conversational response if no tools are required")
    thought: str = Field(default="", description="Reasoning and planning rationale")
    steps: List[PlanStep] = Field(default_factory=list, description="Ordered tool execution steps")


class StepExecutionResult(BaseModel):
    """
    Standardized execution result of an individual tool call executed via MCP.
    """

    step_id: int = Field(default=1, description="Step identifier corresponding to PlanStep.step_id")
    tool_name: str = Field(description="Name of the executed tool")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool")
    raw_content: Any = Field(default=None, description="Raw output content from MCP tool call")
    structured_data: Optional[Dict[str, Any]] = Field(default=None, description="Parsed structured JSON output payload")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extracted domain metadata (CSV table, SQL queries)")
    success: bool = Field(default=True, description="Whether tool execution succeeded")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")


class RawExecutionAnswer(BaseModel):
    """
    Consolidated raw execution outputs and metadata across all plan steps.
    """

    steps: List[StepExecutionResult] = Field(default_factory=list, description="List of individual step execution results")
    raw_text: str = Field(default="", description="Consolidated textual summary across all executed steps")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Consolidated domain metadata (tables and SQL)")


class FinalOrchestratorResult(BaseModel):
    """
    Final synthesized answer presented to the user with domain metadata.
    """

    user_query: str = Field(description="Original user natural language query")
    plan: ExecutionPlan = Field(description="Orchestrator execution plan")
    raw_answer: RawExecutionAnswer = Field(description="Raw tool execution details and outputs")
    final_response: str = Field(description="Final user-facing response synthesized by Orchestrator")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Domain metadata (table, SQL queries)")

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts result into dictionary payload for API responses.
        """
        return {
            "user_query": self.user_query,
            "response": self.final_response,
            "metadata": self.metadata,
            "plan": self.plan.model_dump(),
            "raw_answer": self.raw_answer.model_dump(),
        }
