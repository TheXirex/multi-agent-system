import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agents.orchestrator.models import ExecutionPlan, PlanStep, ToolDefinition
from shared.llm.base import BaseLLM, extract_text_from_message_content

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Planner agent in an advanced AI Multi-Agent Orchestrator.
Your job is to analyze the user's natural language request and determine which available MCP tool or sequence of MCP tools to invoke.

You have access to tools exposed by domain agents via the Model Context Protocol (MCP).

Available tools:
{tools_description}

Guidelines:
1. Carefully analyze what data or action the user is requesting.
2. Formulate a step-by-step plan. If a single tool satisfies the requirement, create a plan with 1 step. If a sequence of tools is required (for example, checking database schema first, then executing SQL), create multiple ordered steps.
3. If the user query is a database question, business analytical question, or data report request:
   - Prefer 'query_and_analyze_database' (arguments: {{"user_input": "<user question>"}}).
4. If the user specifically asks to inspect or see database schema or table structures:
   - Prefer 'get_database_schema' (arguments: {{}}).
5. If the user provides a direct raw SQL statement to run:
   - Prefer 'execute_sql_to_csv' (arguments: {{"query": "<sql query>", "filename": "<optional_name.csv>"}}).
6. If the request is a simple conversational greeting or does not require any tool execution, produce an empty steps list with your reasoning in 'thought'.

Respond strictly with a valid JSON object in the following format:
```json
{{
  "thought": "<your analytical reasoning for the selected plan>",
  "steps": [
    {{
      "step_id": 1,
      "tool_name": "<exact_tool_name>",
      "description": "<short explanation of what this step accomplishes>",
      "arguments": {{
        "<parameter_name>": "<parameter_value>"
      }}
    }}
  ]
}}
```
Do not include any conversational filler outside the JSON.
"""


class Planner:
    """
    Analyzes user requests and constructs execution plans using discovered MCP tools.
    """

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm
        self.chat_model: BaseChatModel = llm.get_chat_model()

    def _format_tools_description(self, tools: List[ToolDefinition]) -> str:
        """
        Formats available MCP tools into a readable specification for the LLM prompt.

        Args:
            tools (List[ToolDefinition]): Discovered tool definitions.

        Returns:
            str: Formatted description text.
        """
        if not tools:
            return "No tools currently registered."

        parts = []
        for t in tools:
            schema_str = json.dumps(t.input_schema, indent=2)
            parts.append(
                f"- Name: {t.name}\n"
                f"  Agent Server: {t.server_name}\n"
                f"  Description: {t.description}\n"
                f"  Input Schema: {schema_str}\n"
            )
        return "\n".join(parts)

    def plan(self, user_query: str, tools: List[ToolDefinition]) -> ExecutionPlan:
        """
        Generates an execution plan for the given user request.

        Args:
            user_query (str): Natural language user instruction.
            tools (List[ToolDefinition]): List of available tools from MCP servers.

        Returns:
            ExecutionPlan: Structured execution plan with sequenced steps.
        """
        tools_desc = self._format_tools_description(tools)
        system_text = PLANNER_SYSTEM_PROMPT.format(tools_description=tools_desc)

        messages = [
            SystemMessage(content=system_text),
            HumanMessage(content=f"User request: {user_query}"),
        ]

        response = self.chat_model.invoke(messages)
        content_text = extract_text_from_message_content(response.content)

        return self._parse_plan_json(content_text, user_query, tools)

    def _parse_plan_json(
        self,
        raw_llm_text: str,
        user_query: str,
        tools: List[ToolDefinition],
    ) -> ExecutionPlan:
        """
        Safely parses LLM JSON output into an ExecutionPlan object with fallback resilience.

        Args:
            raw_llm_text (str): Raw response text from the LLM.
            user_query (str): The original user request.
            tools (List[ToolDefinition]): Available tools list.

        Returns:
            ExecutionPlan: Parsed or fallback execution plan.
        """
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_llm_text)
        candidate = json_match.group(1).strip() if json_match else raw_llm_text.strip()

        try:
            data = json.loads(candidate)
            plan = ExecutionPlan.model_validate(data)
            return plan
        except Exception as err:
            logger.warning(f"Failed to parse planner JSON ({err}). Raw output: {raw_llm_text[:200]}")

        # Fallback: if user asked a database question and query_and_analyze_database is available
        tool_names = {t.name for t in tools}
        if "query_and_analyze_database" in tool_names:
            return ExecutionPlan(
                thought="Fallback to primary database analytical tool due to unparseable plan.",
                steps=[
                    PlanStep(
                        step_id=1,
                        tool_name="query_and_analyze_database",
                        description="Analyze user request against database",
                        arguments={"user_input": user_query},
                    )
                ],
            )

        return ExecutionPlan(thought=raw_llm_text, steps=[])
