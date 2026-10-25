import asyncio
import contextvars
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional


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
from agents.orchestrator.utils import (
    consolidate_step_metadata,
    create_guardrail_refusal_response,
    extract_step_text,
    format_tools_description,
    is_in_scope,
    resolve_tool_arguments,
)
from shared.llm.base import BaseLLM, extract_text_from_message_content
from shared.llm.factory import LLMFactory
from shared.tools import get_tool_action_label

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
        workflow.add_node("guardrail_refusal", self._guardrail_refusal_node)

        # Edges
        workflow.add_edge(START, "route_and_plan")
        workflow.add_conditional_edges(
            "route_and_plan",
            self._route_after_planning,
            {
                "execute": "execute_tools",
                "direct": "direct_response",
                "refusal": "guardrail_refusal",
            },
        )
        workflow.add_edge("direct_response", END)
        workflow.add_edge("guardrail_refusal", END)
        workflow.add_edge("execute_tools", "synthesize_response")
        workflow.add_edge("synthesize_response", END)

        return workflow.compile()

    async def _route_and_plan_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Node that determines if query requires tools or should be answered directly
        using model-level structured output bound to ExecutionPlan.
        """
        user_query = state.get("user_query", "")
        tools = state.get("tools", [])
        conversation_history = state.get("conversation_history", [])
        active_metadata = state.get("active_metadata", {})

        tools_desc = format_tools_description(tools)
        system_text = prompt_loader.render(
            "routing",
            tools_description=tools_desc,
            conversation_history=conversation_history,
            active_metadata=active_metadata,
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

            if not plan.is_in_scope:
                plan.requires_tools = False
                plan.steps = []
            elif not plan.steps:
                plan.requires_tools = False
                if not plan.direct_response and plan.thought:
                    plan.direct_response = plan.thought

            return {
                "is_in_scope": plan.is_in_scope,
                "rejection_reason": plan.rejection_reason,
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
                "is_in_scope": True,
                "rejection_reason": None,
                "requires_tools": False,
                "direct_response": text,
                "thought": "",
                "steps": [],
            }

    def _route_after_planning(self, state: OrchestratorState) -> Literal["execute", "direct", "refusal"]:
        """
        Conditional edge: routes to tool execution, direct conversational answer,
        or guardrail refusal for out-of-scope requests.
        """
        if not is_in_scope(state):
            return "refusal"
        if state.get("requires_tools") and state.get("steps"):
            return "execute"
        return "direct"

    async def _guardrail_refusal_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Guardrail node: handles rejected out-of-scope queries deterministically,
        preventing any tool execution and returning a polite refusal.
        """
        return create_guardrail_refusal_response(state)

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

        sess_id = (state.get("active_metadata") or {}).get("session_id") or (state.get("metadata") or {}).get("session_id")
        return {
            "final_response": direct_text,
            "raw_text": "",
            "metadata": {"session_id": sess_id} if sess_id else {},
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
        active_meta = dict(state.get("active_metadata") or {})
        session_id = active_meta.get("session_id")
        consolidated_metadata: Dict[str, Any] = {"session_id": session_id} if session_id else {}
        last_dataset_id: Optional[int] = active_meta.get("dataset_id")
        last_exported_csv: Optional[str] = None

        for step in steps:
            logger.info(f"Executing step {step.step_id}: {step.tool_name}")

            step_args = resolve_tool_arguments(
                tool_name=step.tool_name,
                raw_arguments=step.arguments,
                active_metadata=active_meta,
                session_id=session_id,
                last_dataset_id=last_dataset_id,
                last_exported_csv=last_exported_csv,
            )

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

            step_text = extract_step_text(result)
            if step_text:
                raw_text_parts.append(step_text)

            last_dataset_id, last_exported_csv = consolidate_step_metadata(
                result=result,
                consolidated_metadata=consolidated_metadata,
                last_dataset_id=last_dataset_id,
                last_exported_csv=last_exported_csv,
            )
            active_meta.update(consolidated_metadata)

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
        metadata = state.get("metadata") or {}

        # If a tool (like ML agent) requested user clarification, output the questions directly
        if metadata.get("status") == "clarification_needed":
            return {"final_response": raw_text, "metadata": metadata}

        prompt_content = (
            f"User Question: {user_query}\n\n"
            f"Tool Execution Results:\n{raw_text}\n"
        )

        messages = [
            SystemMessage(
                content=prompt_loader.render(
                    "synthesis",
                    conversation_history=state.get("conversation_history", []),
                )
            ),
            HumanMessage(content=prompt_content),
        ]

        try:
            response = await self.chat_model.ainvoke(messages)
            final_text = extract_text_from_message_content(response.content)
        except Exception as exc:
            logger.error(f"Error synthesizing response in Orchestrator: {exc}")
            final_text = raw_text or "Execution completed."

        return {"final_response": final_text, "metadata": metadata}

    async def run(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        active_metadata: Optional[Dict[str, Any]] = None,
    ) -> FinalOrchestratorResult:
        """
        Asynchronously runs Orchestrator LangGraph pipeline:
        1. Connects to MCP servers and discovers available tools.
        2. Routes request (direct answer vs MCP tool execution) incorporating conversation history & active metadata.
        3. Returns structured FinalOrchestratorResult with metadata.

        Args:
            user_query (str): The natural language query from user.
            conversation_history (Optional[List[Dict[str, str]]]): Recent messages for context.
            active_metadata (Optional[Dict[str, Any]]): Currently active dataset/chart IDs in memory.

        Returns:
            FinalOrchestratorResult: Response containing answer, plan, and metadata.
        """
        logger.info(f"Orchestrator received query: {user_query}")
        if conversation_history:
            logger.info(f"Orchestrator with {len(conversation_history)} history messages and active metadata: {active_metadata}")

        async with self.mcp_manager.open_session() as session:
            tools = await session.list_tools()
            logger.info(f"Discovered {len(tools)} tools via MCP: {[t.name for t in tools]}")

            sess_id = (active_metadata or {}).get("session_id")
            initial_state: OrchestratorState = {
                "user_query": user_query,
                "tools": tools,
                "conversation_history": conversation_history or [],
                "active_metadata": active_metadata or {},
                "is_in_scope": True,
                "rejection_reason": None,
                "requires_tools": False,
                "direct_response": "",
                "thought": "",
                "steps": [],
                "execution_results": [],
                "raw_text": "",
                "metadata": {"session_id": sess_id} if sess_id else {},
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
                    is_in_scope=final_state.get("is_in_scope", True),
                    rejection_reason=final_state.get("rejection_reason"),
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

    def run_sync(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        active_metadata: Optional[Dict[str, Any]] = None,
    ) -> FinalOrchestratorResult:
        """
        Synchronous execution helper for CLI or non-async environments.
        """
        try:
            return asyncio.run(
                self.run(
                    user_query,
                    conversation_history=conversation_history,
                    active_metadata=active_metadata,
                )
            )
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.run(
                    user_query,
                    conversation_history=conversation_history,
                    active_metadata=active_metadata,
                )
            )

    async def process_query(
        self,
        query: str,
        history: Optional[List[Dict[str, Any]]] = None,
        active_metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> FinalOrchestratorResult:
        """
        Async entrypoint for API routes processing queries with session-scoping.
        """
        meta = dict(active_metadata or {})
        if session_id:
            meta["session_id"] = session_id
        return await self.run(
            user_query=query,
            conversation_history=history,
            active_metadata=meta,
        )

    async def process_query_stream(
        self,
        query: str,
        history: Optional[List[Dict[str, Any]]] = None,
        active_metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streaming execution entrypoint yielding real-time step action updates and final result.
        """
        meta = dict(active_metadata or {})
        if session_id:
            meta["session_id"] = session_id

        yield {
            "type": "status",
            "status": "planning",
            "action": "Planning execution steps...",
        }

        async with self.mcp_manager.open_session() as session:
            tools = await session.list_tools()
            initial_state: OrchestratorState = {
                "user_query": query,
                "tools": tools,
                "conversation_history": history or [],
                "active_metadata": meta,
                "is_in_scope": True,
                "rejection_reason": None,
                "requires_tools": False,
                "direct_response": "",
                "thought": "",
                "steps": [],
                "execution_results": [],
                "raw_text": "",
                "metadata": {"session_id": session_id} if session_id else {},
                "final_response": "",
                "error": None,
            }

            token = _current_mcp_session.set(session)
            try:
                # 1. Route and plan
                planned_state = await self._route_and_plan_node(initial_state)
                initial_state.update(planned_state)

                route_decision = self._route_after_planning(initial_state)

                if route_decision == "refusal":
                    refusal_res = await self._guardrail_refusal_node(initial_state)
                    yield {
                        "type": "result",
                        "response": refusal_res.get("final_response", ""),
                        "metadata": refusal_res.get("metadata") or ({"session_id": session_id} if session_id else {}),
                        "session_id": session_id,
                    }
                    return

                if route_decision == "direct":
                    yield {
                        "type": "status",
                        "status": "direct",
                        "action": "Formulating response...",
                    }
                    direct_res = await self._direct_response_node(initial_state)
                    yield {
                        "type": "result",
                        "response": direct_res.get("final_response", ""),
                        "metadata": direct_res.get("metadata") or ({"session_id": session_id} if session_id else {}),
                        "session_id": session_id,
                    }
                    return

                # 2. Execute tools step-by-step, yielding dynamic action labels
                steps = initial_state.get("steps", [])
                step_results: List[StepExecutionResult] = []
                raw_text_parts: List[str] = []
                active_meta = dict(initial_state.get("active_metadata") or {})
                sess_id = active_meta.get("session_id")
                consolidated_metadata: Dict[str, Any] = {"session_id": sess_id} if sess_id else {}
                last_dataset_id: Optional[int] = active_meta.get("dataset_id")
                last_exported_csv: Optional[str] = None

                for step in steps:
                    action_label = get_tool_action_label(step.tool_name)
                    yield {
                        "type": "status",
                        "status": "executing",
                        "tool_name": step.tool_name,
                        "step_id": step.step_id,
                        "action": action_label,
                    }

                    step_args = resolve_tool_arguments(
                        tool_name=step.tool_name,
                        raw_arguments=step.arguments,
                        active_metadata=active_meta,
                        session_id=sess_id,
                        last_dataset_id=last_dataset_id,
                        last_exported_csv=last_exported_csv,
                    )

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

                    step_text = extract_step_text(result)
                    if step_text:
                        raw_text_parts.append(step_text)

                    last_dataset_id, last_exported_csv = consolidate_step_metadata(
                        result=result,
                        consolidated_metadata=consolidated_metadata,
                        last_dataset_id=last_dataset_id,
                        last_exported_csv=last_exported_csv,
                    )
                    active_meta.update(consolidated_metadata)

                combined_raw = "\n\n".join(raw_text_parts) if raw_text_parts else "No tools executed."
                initial_state["execution_results"] = step_results
                initial_state["raw_text"] = combined_raw
                initial_state["metadata"] = consolidated_metadata

                # 3. Check if clarification is needed (e.g. from modify_table or ingest_file)
                clarification_response = None
                for res in step_results:
                    data = res.structured_data if isinstance(res.structured_data, dict) else {}
                    if data.get("status") == "clarification_needed":
                        clarification_response = data.get("response") or data.get("message")
                        break

                if clarification_response:
                    yield {
                        "type": "result",
                        "response": clarification_response,
                        "metadata": consolidated_metadata,
                        "session_id": session_id,
                    }
                    return

                # 4. Synthesize final response
                yield {
                    "type": "status",
                    "status": "synthesizing",
                    "action": "Synthesizing response...",
                }
                synth_res = await self._synthesize_response_node(initial_state)
                final_meta = synth_res.get("metadata") or initial_state.get("metadata") or consolidated_metadata or {}
                yield {
                    "type": "result",
                    "response": synth_res.get("final_response", ""),
                    "metadata": final_meta,
                    "session_id": session_id,
                }
            finally:
                _current_mcp_session.reset(token)




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

