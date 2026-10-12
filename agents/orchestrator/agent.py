import asyncio
import contextvars
import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional


from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from agents.orchestrator.client import ActiveMCPSession, MCPClientManager
from agents.orchestrator.config import OrchestratorSettings, get_orchestrator_settings
from agents.orchestrator.models import (
    ExecutionPlan,
    FinalOrchestratorResult,
    OrchestratorState,
    PlanStep,
    RawExecutionAnswer,
    StepExecutionResult,
    ToolDefinition,
)
from agents.orchestrator.prompts import prompt_loader
from shared.llm.base import BaseLLM, extract_text_from_message_content
from shared.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

# Context variable to hold active MCP session across async graph nodes
_current_mcp_session: contextvars.ContextVar[Optional[ActiveMCPSession]] = contextvars.ContextVar(
    "_current_mcp_session", default=None
)


class OrchestratorAgent:
    """
    LangGraph-powered Orchestrator Agent that acts as an MCP client, coordinating
    conversational routing, tool execution across domain agents, and response synthesis.
    """

    def __init__(
        self,
        llm: BaseLLM,
        mcp_manager: Optional[MCPClientManager] = None,
    ) -> None:
        self.llm = llm
        self.chat_model: BaseChatModel = llm.get_chat_model()
        self.mcp_manager = mcp_manager or MCPClientManager()
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """
        Constructs the LangGraph state graph for Orchestrator execution.

        Returns:
            CompiledStateGraph: The compiled runnable state graph.
        """
        workflow = StateGraph(OrchestratorState)

        # Graph nodes
        workflow.add_node("route_and_plan", self._route_and_plan_node)
        workflow.add_node("direct_response", self._direct_response_node)
        workflow.add_node("execute_tools", self._execute_tools_node)
        workflow.add_node("synthesize_response", self._synthesize_response_node)

        # Edges
        workflow.add_edge(START, "route_and_plan")
        workflow.add_conditional_edges(
            "route_and_plan",
            self._route_after_planning,
            {
                "execute": "execute_tools",
                "direct": "direct_response",
            },
        )
        workflow.add_edge("direct_response", END)
        workflow.add_edge("execute_tools", "synthesize_response")
        workflow.add_edge("synthesize_response", END)

        return workflow.compile()

    def _format_tools_description(self, tools: List[ToolDefinition]) -> str:
        """
        Formats available MCP tools into a readable specification for routing prompt.
        """
        if not tools:
            return "No tools currently registered."

        lines = []
        for t in tools:
            schema_params = t.input_schema.get("properties", {})
            required_params = t.input_schema.get("required", [])
            params_str = ", ".join(
                f"{k}: {v.get('type', 'any')}{' (required)' if k in required_params else ''}"
                for k, v in schema_params.items()
            )
            lines.append(f"- '{t.name}' (server: {t.server_name}): {t.description}")
            if params_str:
                lines.append(f"  Arguments: {{{params_str}}}")
        return "\n".join(lines)

    async def _route_and_plan_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Node that determines if query requires tools or should be answered directly
        using model-level structured output bound to ExecutionPlan.
        """
        user_query = state.get("user_query", "")
        tools = state.get("tools", [])

        tools_desc = self._format_tools_description(tools)
        system_text = prompt_loader.render(
            "routing",
            tools_description=tools_desc,
        )

        messages = [
            SystemMessage(content=system_text),
            HumanMessage(content=f"User request: {user_query}"),
        ]

        try:
            structured_model = self.chat_model.with_structured_output(ExecutionPlan)
            plan = await structured_model.ainvoke(messages)

            if isinstance(plan, dict):
                plan = ExecutionPlan.model_validate(plan)

            if not plan.steps:
                plan.requires_tools = False
                if not plan.direct_response and plan.thought:
                    plan.direct_response = plan.thought

            return {
                "requires_tools": plan.requires_tools,
                "direct_response": plan.direct_response,
                "thought": plan.thought,
                "steps": plan.steps,
            }
        except Exception as err:
            logger.warning(f"Structured plan extraction failed ({err}), falling back to direct response.")
            resp = await self.chat_model.ainvoke(messages)
            text = extract_text_from_message_content(resp.content)
            return {
                "requires_tools": False,
                "direct_response": text,
                "thought": "",
                "steps": [],
            }

    def _route_after_planning(self, state: OrchestratorState) -> Literal["execute", "direct"]:
        """
        Conditional edge: routes to tool execution or direct conversational answer.
        """
        if state.get("requires_tools") and state.get("steps"):
            return "execute"
        return "direct"

    async def _direct_response_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Node that completes conversational answer when no domain tools are needed.
        """
        direct_text = state.get("direct_response") or state.get("thought", "")
        if not direct_text.strip():
            direct_prompt = prompt_loader.render("direct")
            messages = [
                SystemMessage(content=direct_prompt),
                HumanMessage(content=state.get("user_query", "")),
            ]
            resp = await self.chat_model.ainvoke(messages)
            direct_text = extract_text_from_message_content(resp.content)

        return {
            "final_response": direct_text,
            "raw_text": "",
            "metadata": {},
            "execution_results": [],
        }

    async def _execute_tools_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Node that executes planned steps via the active MCP session.
        """
        session = _current_mcp_session.get()
        if not session:
            raise RuntimeError("Active MCP session is not available in execution node.")

        steps = state.get("steps", [])
        step_results: List[StepExecutionResult] = []
        raw_text_parts: List[str] = []
        consolidated_metadata: Dict[str, Any] = {}

        last_dataset_id: Optional[int] = None
        last_exported_csv: Optional[str] = None

        for step in steps:
            logger.info(f"Executing step {step.step_id}: {step.tool_name}")

            # Dynamic argument resolution: inject previous step's dataset_id or CSV output if required
            step_args = dict(step.arguments or {})
            if "dataset_id" in step_args:
                val = step_args.get("dataset_id")
                if (val is None or val == "" or str(val).lower() in {"0", "latest", "{{dataset_id}}"}) and last_dataset_id:
                    step_args["dataset_id"] = last_dataset_id
            elif last_dataset_id and "dataset_id" not in step_args and step.tool_name == "run_ml_analysis":
                step_args["dataset_id"] = last_dataset_id

            if "dataset_path" in step_args:
                val = str(step_args.get("dataset_path", "")).strip()
                if (not val or val.lower() in {"", "latest", "{{csv}}", "{{previous_step_csv}}", "{{file_path}}"}) and last_exported_csv:
                    step_args["dataset_path"] = last_exported_csv

            result = await session.call_tool(
                tool_name=step.tool_name,
                arguments=step_args,
                step_id=step.step_id,
            )
            step_results.append(result)

            if not result.success:
                logger.warning(f"Step {step.step_id} failed: {result.error}")
                raw_text_parts.append(f"[Step {step.step_id} - Error]: {result.error}")
                continue

            step_text = ""
            if result.structured_data and isinstance(result.structured_data, dict):
                resp_text = result.structured_data.get("response") or result.structured_data.get("schema")
                if resp_text:
                    step_text = str(resp_text)
                else:
                    step_text = json.dumps(result.structured_data, indent=2, default=str)
            elif result.raw_content:
                step_text = str(result.raw_content)

            if step_text:
                raw_text_parts.append(step_text)

            # Consolidate strictly ID-only metadata
            if result.metadata:
                if "dataset_id" in result.metadata and result.metadata["dataset_id"]:
                    last_dataset_id = result.metadata["dataset_id"]
                    consolidated_metadata["dataset_id"] = result.metadata["dataset_id"]
                if "chart_id" in result.metadata and result.metadata["chart_id"]:
                    consolidated_metadata["chart_id"] = result.metadata["chart_id"]
                if "chart_ids" in result.metadata and result.metadata["chart_ids"]:
                    consolidated_metadata["chart_ids"] = result.metadata["chart_ids"]
                if "script_id" in result.metadata and result.metadata["script_id"]:
                    consolidated_metadata["script_id"] = result.metadata["script_id"]

            if result.structured_data and isinstance(result.structured_data, dict):
                sd = result.structured_data
                if "dataset_id" in sd and sd["dataset_id"]:
                    last_dataset_id = sd["dataset_id"]
                    consolidated_metadata.setdefault("dataset_id", sd["dataset_id"])
                if "chart_id" in sd and sd["chart_id"]:
                    consolidated_metadata.setdefault("chart_id", sd["chart_id"])
                if "chart_ids" in sd and sd["chart_ids"]:
                    consolidated_metadata.setdefault("chart_ids", sd["chart_ids"])
                if "script_id" in sd and sd["script_id"]:
                    consolidated_metadata.setdefault("script_id", sd["script_id"])
                if "file_path" in sd and sd["file_path"]:
                    last_exported_csv = sd["file_path"]

        combined_raw = "\n\n".join(raw_text_parts) if raw_text_parts else "No tools executed."

        return {
            "execution_results": step_results,
            "raw_text": combined_raw,
            "metadata": consolidated_metadata,
        }


    async def _synthesize_response_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Node that synthesizes the final user-facing response from tool execution outputs.
        """
        user_query = state.get("user_query", "")
        raw_text = state.get("raw_text", "")

        prompt_content = (
            f"User Question: {user_query}\n\n"
            f"Tool Execution Results:\n{raw_text}\n"
        )

        messages = [
            SystemMessage(content=prompt_loader.render("synthesis")),
            HumanMessage(content=prompt_content),
        ]

        try:
            response = await self.chat_model.ainvoke(messages)
            final_text = extract_text_from_message_content(response.content)
        except Exception as exc:
            logger.error(f"Error synthesizing response in Orchestrator: {exc}")
            final_text = raw_text or "Execution completed."

        return {"final_response": final_text}

    async def run(self, user_query: str) -> FinalOrchestratorResult:
        """
        Asynchronously runs Orchestrator LangGraph pipeline:
        1. Connects to MCP servers and discovers available tools.
        2. Routes request (direct answer vs MCP tool execution).
        3. Returns structured FinalOrchestratorResult with metadata.

        Args:
            user_query (str): The natural language query from user.

        Returns:
            FinalOrchestratorResult: Response containing answer, plan, and metadata.
        """
        logger.info(f"Orchestrator received query: {user_query}")

        async with self.mcp_manager.open_session() as session:
            tools = await session.list_tools()
            logger.info(f"Discovered {len(tools)} tools via MCP: {[t.name for t in tools]}")

            initial_state: OrchestratorState = {
                "user_query": user_query,
                "tools": tools,
                "requires_tools": False,
                "direct_response": "",
                "thought": "",
                "steps": [],
                "execution_results": [],
                "raw_text": "",
                "metadata": {},
                "final_response": "",
                "error": None,
            }

            token = _current_mcp_session.set(session)
            try:
                final_state = await self.graph.ainvoke(initial_state)
            finally:
                _current_mcp_session.reset(token)

            return FinalOrchestratorResult(
                user_query=user_query,
                plan=ExecutionPlan(
                    requires_tools=final_state.get("requires_tools", False),
                    direct_response=final_state.get("direct_response", ""),
                    thought=final_state.get("thought", ""),
                    steps=final_state.get("steps", []),
                ),
                raw_answer=RawExecutionAnswer(
                    steps=final_state.get("execution_results", []),
                    raw_text=final_state.get("raw_text", ""),
                    metadata=final_state.get("metadata", {}),
                ),
                final_response=final_state.get("final_response", ""),
                metadata=final_state.get("metadata", {}),
            )

    def run_sync(self, user_query: str) -> FinalOrchestratorResult:
        """
        Synchronous execution helper for CLI or non-async environments.
        """
        try:
            return asyncio.run(self.run(user_query))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.run(user_query))



def create_orchestrator(
    settings: Optional[OrchestratorSettings] = None,
    llm: Optional[BaseLLM] = None,
    mcp_manager: Optional[MCPClientManager] = None,
) -> OrchestratorAgent:
    """
    Factory function to construct a fully configured OrchestratorAgent.

    Args:
        settings (Optional[OrchestratorSettings]): Custom OrchestratorSettings instance.
        llm (Optional[BaseLLM]): Pre-configured LLM instance.
        mcp_manager (Optional[MCPClientManager]): Custom MCPClientManager instance.

    Returns:
        OrchestratorAgent: Initialized orchestrator agent.
    """
    cfg = settings or get_orchestrator_settings()
    active_llm = llm or LLMFactory.create(
        provider=cfg.llm_provider,
        model_name=cfg.llm_model,
        api_key=cfg.llm_api_key,
    )
    manager = mcp_manager or MCPClientManager()

    return OrchestratorAgent(
        llm=active_llm,
        mcp_manager=manager,
    )


build_orchestrator = create_orchestrator

