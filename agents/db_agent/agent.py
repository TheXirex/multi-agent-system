import json
import re
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from agents.db_agent.db.inspector import DatabaseInspector
from agents.db_agent.tools.registry import ToolRegistry
from shared.llm.base import BaseLLM, extract_text_from_message_content



class AgentState(TypedDict):
    """
    State container for the LangGraph database agent workflow.
    """

    user_input: str
    schema: str
    sql_query: str
    tool_result: Dict[str, Any]
    response: str
    error: Optional[str]
    retry_count: int


class DBAgent:
    """
    LangGraph-based database agent that coordinates schema inspection, SQL generation,
    tool execution, and analytical response synthesis.
    """

    def __init__(
        self,
        llm: BaseLLM,
        inspector: DatabaseInspector,
        tools: ToolRegistry,
        max_retries: int = 2,
    ) -> None:
        self.llm = llm
        self.chat_model: BaseChatModel = llm.get_chat_model()
        self.inspector = inspector
        self.tools = tools
        self.max_retries = max_retries
        self.graph = self._build_graph()

    def run(self, user_request: str) -> Dict[str, Any]:
        """
        Executes the LangGraph agent workflow for the given user request.

        Args:
            user_request (str): Natural language user requirement.

        Returns:
            Dict[str, Any]: Final graph state containing execution details and response.
        """
        initial_state: AgentState = {
            "user_input": user_request,
            "schema": "",
            "sql_query": "",
            "tool_result": {},
            "response": "",
            "error": None,
            "retry_count": 0,
        }
        return self.graph.invoke(initial_state)

    def query_database_and_analyze(self, user_input: str) -> Dict[str, Any]:
        """
        Analyzes database content based on user request, executes query, and returns a structured response with metadata.

        Args:
            user_input (str): Natural language instruction or analytical question.

        Returns:
            Dict[str, Any]: Structured dictionary with response, table metadata (path, rows, cols), and SQL code.
        """
        final_state = self.run(user_input)
        tool_result = final_state.get("tool_result") or {}

        table_metadata = {
            "file_path": tool_result.get("file_path", ""),
            "file_name": tool_result.get("file_name", ""),
            "row_count": tool_result.get("row_count", 0),
            "columns": tool_result.get("columns", []),
        }

        code_metadata = {
            "language": "sql",
            "query": final_state.get("sql_query", ""),
        }

        return {
            "response": final_state.get("response", ""),
            "metadata": {
                "table": table_metadata,
                "code": code_metadata,
            },
        }

    def _build_graph(self) -> Any:
        """
        Constructs and compiles the LangGraph StateGraph workflow for database query processing.

        Args:
            None

        Returns:
            Any: Compiled LangGraph runnable.
        """
        workflow = StateGraph(AgentState)

        workflow.add_node("inspect_schema", self._inspect_schema_node)
        workflow.add_node("generate_sql", self._generate_sql_node)
        workflow.add_node("execute_sql", self._execute_sql_node)
        workflow.add_node("generate_response", self._generate_response_node)

        workflow.add_edge(START, "inspect_schema")
        workflow.add_edge("inspect_schema", "generate_sql")
        workflow.add_edge("generate_sql", "execute_sql")
        workflow.add_conditional_edges(
            "execute_sql",
            self._route_after_execution,
            {
                "retry": "generate_sql",
                "respond": "generate_response",
            },
        )
        workflow.add_edge("generate_response", END)

        return workflow.compile()

    def _inspect_schema_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Graph node that fetches database schema definitions.

        Args:
            state (AgentState): Current graph state.

        Returns:
            Dict[str, Any]: State updates with retrieved schema context.
        """
        schema_summary = self.inspector.get_schema_summary()
        return {"schema": schema_summary}

    def _generate_sql_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Graph node that generates SQL query using LangChain chat model.

        Args:
            state (AgentState): Current graph state with schema and user input.

        Returns:
            Dict[str, Any]: State updates with extracted SQL query.
        """
        error_context = ""
        if state.get("error"):
            error_context = (
                f"\nPrevious execution failed with error: {state['error']}.\n"
                f"Previous SQL was: {state.get('sql_query')}.\n"
                "Please fix the SQL query to resolve this error."
            )

        system_prompt = (
            "You are an expert PostgreSQL database analyst. "
            "Write a valid PostgreSQL query to answer the user request based on the provided schema.\n"
            "Return ONLY the SQL query without any Markdown formatting, explanations, or quotes."
        )

        user_content = (
            f"Database Schema:\n{state['schema']}\n\n"
            f"User Request: {state['user_input']}"
            f"{error_context}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]
        ai_response = self.chat_model.invoke(messages)
        raw_text = extract_text_from_message_content(ai_response.content)
        sql = self._clean_sql_query(raw_text)

        return {"sql_query": sql}

    def _execute_sql_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Graph node that executes generated SQL query via ExecuteSQLAndExportCSVTool.

        Args:
            state (AgentState): Current graph state with sql_query.

        Returns:
            Dict[str, Any]: State updates containing tool result and optional error.
        """
        sql_query = state.get("sql_query", "")
        tool_result = self.tools.execute("execute_sql_to_csv", query=sql_query)

        error = tool_result.get("error") if tool_result.get("status") == "error" else None
        current_retries = state.get("retry_count", 0)

        return {
            "tool_result": tool_result,
            "error": error,
            "retry_count": current_retries + 1 if error else current_retries,
        }

    def _generate_response_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Graph node that synthesizes an analytical answer based on user query and execution results.

        Args:
            state (AgentState): Current graph state with tool result and query.

        Returns:
            Dict[str, Any]: State updates with generated response text.
        """
        tool_result = state.get("tool_result") or {}
        preview_data = tool_result.get("preview", [])
        columns = tool_result.get("columns", [])
        row_count = tool_result.get("row_count", 0)

        system_prompt = (
            "You are a helpful data analyst. Analyze the executed SQL query and exported dataset, "
            "and provide a concise, informative response explaining the findings to the user."
        )

        user_content = (
            f"User Request: {state['user_input']}\n"
            f"SQL Executed: {state.get('sql_query')}\n"
            f"Rows Count: {row_count}\n"
            f"Columns: {columns}\n"
            f"Sample Data Preview: {json.dumps(preview_data, default=str)}\n\n"
            "Provide a clear summary of the findings."
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]
        ai_response = self.chat_model.invoke(messages)
        response_text = extract_text_from_message_content(ai_response.content)
        return {"response": response_text}

    def _route_after_execution(self, state: AgentState) -> Literal["retry", "respond"]:
        """
        Conditional edge routing: loops back to generate_sql on error if retries remain, else proceeds to respond.

        Args:
            state (AgentState): Current graph state containing execution status and retry count.

        Returns:
            Literal["retry", "respond"]: Next graph node identifier.
        """
        if state.get("error") and state.get("retry_count", 0) <= self.max_retries:
            return "retry"
        return "respond"

    def _clean_sql_query(self, text: str) -> str:
        """
        Strips markdown code blocks, prefixes, and whitespace from model SQL output.

        Args:
            text (str): Raw model output string.

        Returns:
            str: Cleaned executable SQL statement.
        """
        cleaned = text.strip()
        code_match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if code_match:
            cleaned = code_match.group(1).strip()
        if cleaned.lower().startswith("sql"):
            cleaned = cleaned[3:].strip()
        return cleaned
