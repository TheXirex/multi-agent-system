import asyncio
import logging
from typing import Any, Dict, Optional

from agents.orchestrator.executor import Executor
from agents.orchestrator.finalizer import Finalizer
from agents.orchestrator.mcp_client import MCPClientManager
from agents.orchestrator.models import FinalOrchestratorResult
from agents.orchestrator.planner import Planner
from shared.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """
    Main Orchestrator Agent that acts as an MCP client, coordinating the
    Planner -> Executor -> Finalizer workflow across MCP-enabled domain agents.
    """

    def __init__(
        self,
        llm: BaseLLM,
        mcp_manager: Optional[MCPClientManager] = None,
    ) -> None:
        self.llm = llm
        self.mcp_manager = mcp_manager or MCPClientManager()
        self.planner = Planner(llm=self.llm)
        self.executor = Executor()
        self.finalizer = Finalizer(llm=self.llm)

    async def run(self, user_query: str) -> FinalOrchestratorResult:
        """
        Asynchronously runs the full orchestration pipeline:
        1. Discovers tools from MCP server(s).
        2. Planner creates execution plan.
        3. Executor calls MCP tools and waits for domain agents to finish.
        4. Finalizer synthesizes raw answer & metadata for user.

        Args:
            user_query (str): The natural language query from the user/UI.

        Returns:
            FinalOrchestratorResult: Final user response with plan, raw outputs, and table/code metadata.
        """
        logger.info(f"Orchestrator received query: {user_query}")

        async with self.mcp_manager.open_session() as session:
            # 1. MCP Tool discovery
            tools = await session.list_tools()
            logger.info(f"Discovered {len(tools)} tools via MCP: {[t.name for t in tools]}")

            # 2. Planner: creates plan based on user input and available tools
            plan = self.planner.plan(user_query=user_query, tools=tools)
            logger.info(f"Planner formulated {len(plan.steps)} steps. Reasoning: {plan.thought}")

            # 3. Executor: runs tool calls via MCP and collects raw answer & metadata
            raw_answer = await self.executor.execute_plan(plan=plan, session=session)
            logger.info(f"Executor completed {len(raw_answer.steps)} steps.")

            # 4. Finalizer: synthesizes final response for UI/user
            result = self.finalizer.finalize(
                user_query=user_query,
                plan=plan,
                raw_answer=raw_answer,
            )
            return result

    def run_sync(self, user_query: str) -> FinalOrchestratorResult:
        """
        Synchronous execution helper for CLI or non-async environments.

        Args:
            user_query (str): The natural language query.

        Returns:
            FinalOrchestratorResult: Final orchestration result.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.run(user_query))
            return loop.run_until_complete(self.run(user_query))
        except RuntimeError:
            return asyncio.run(self.run(user_query))
