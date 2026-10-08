import json
import logging
from typing import Any, Dict, List, Optional

from agents.orchestrator.mcp_client import ActiveMCPSession
from agents.orchestrator.models import ExecutionPlan, RawExecutionAnswer, StepExecutionResult

logger = logging.getLogger(__name__)


class Executor:
    """
    Executes sequenced tool steps in an ExecutionPlan by calling tools via active MCP sessions.
    Collects raw execution answers and domain metadata.
    """

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        session: ActiveMCPSession,
    ) -> RawExecutionAnswer:
        """
        Executes each planned step sequentially over active MCP sessions.

        Args:
            plan (ExecutionPlan): Sequenced plan created by Planner.
            session (ActiveMCPSession): Active MCP connection session.

        Returns:
            RawExecutionAnswer: Consolidated results and domain metadata.
        """
        step_results: List[StepExecutionResult] = []
        raw_text_parts: List[str] = []
        consolidated_metadata: Dict[str, Any] = {
            "table": {},
            "code": {},
        }

        for step in plan.steps:
            logger.info(f"Executing step {step.step_id}: {step.tool_name} ({step.description})")

            # Call the tool via MCP
            result = await session.call_tool(
                tool_name=step.tool_name,
                arguments=step.arguments,
                step_id=step.step_id,
            )
            step_results.append(result)

            if not result.success:
                logger.warning(f"Step {step.step_id} ({step.tool_name}) failed: {result.error}")
                raw_text_parts.append(f"[Step {step.step_id} - Error]: {result.error}")
                continue

            # Accumulate text output
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

            # Consolidate metadata
            if result.metadata:
                if "table" in result.metadata and result.metadata["table"]:
                    consolidated_metadata["table"].update(result.metadata["table"])
                if "code" in result.metadata and result.metadata["code"]:
                    consolidated_metadata["code"].update(result.metadata["code"])

            # Check inside structured_data directly for table or SQL metadata
            if result.structured_data:
                sd = result.structured_data
                if "file_path" in sd:
                    consolidated_metadata["table"].setdefault("file_path", sd.get("file_path", ""))
                    consolidated_metadata["table"].setdefault("file_name", sd.get("file_name", ""))
                    consolidated_metadata["table"].setdefault("row_count", sd.get("row_count", 0))
                    consolidated_metadata["table"].setdefault("columns", sd.get("columns", []))
                    consolidated_metadata["table"].setdefault("preview", sd.get("preview", []))

                if "sql_query" in sd or "query" in sd:
                    consolidated_metadata["code"].setdefault("language", "sql")
                    consolidated_metadata["code"].setdefault("query", sd.get("sql_query") or sd.get("query", ""))

        # Clean empty metadata dictionaries
        clean_metadata: Dict[str, Any] = {}
        for k, v in consolidated_metadata.items():
            if v:
                clean_metadata[k] = v

        combined_raw = "\n\n".join(raw_text_parts) if raw_text_parts else "No tools executed."

        return RawExecutionAnswer(
            steps=step_results,
            raw_text=combined_raw,
            metadata=clean_metadata,
        )
