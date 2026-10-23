import json
import logging
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import text

from agents.db_agent.config import Settings, get_settings
from agents.db_agent.db import DatabaseInspector, create_db_engine
from agents.db_agent.prompts import prompt_loader
from agents.db_agent.utils.schemas import SQLGenerationOutput
from agents.db_agent.tools import (
    ExecuteSQLAndExportCSVTool,
    IngestTabularFileTool,
    ModifyDatabaseTableTool,
    RollbackDatabaseChangeTool,
    ToolRegistry,
)
from shared.llm.base import BaseLLM, extract_text_from_message_content
from shared.llm.factory import LLMFactory
from shared.metadata import truncate_words

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """
    State container for the LangGraph database agent workflow.
    """

    user_input: str
    schema: str
    sql_query: str
    table_name: str
    sql_description: str
    tool_result: Dict[str, Any]
    response: str
    error: Optional[str]
    retry_count: int
    session_id: Optional[str]


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

    def run(self, user_request: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes the LangGraph agent workflow for the given user request.

        Args:
            user_request (str): Natural language user requirement.
            session_id (Optional[str]): Optional active session ID for session schema replica.

        Returns:
            Dict[str, Any]: Final graph state containing execution details and response.
        """
        initial_state: AgentState = {
            "user_input": user_request,
            "schema": "",
            "sql_query": "",
            "table_name": "",
            "sql_description": "",
            "tool_result": {},
            "response": "",
            "error": None,
            "retry_count": 0,
            "session_id": session_id,
        }
        return self.graph.invoke(initial_state)

    def _save_sql_script(
        self,
        script: str,
        sql_description: str,
        dataset_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Persists generated SQL query into PostgreSQL generated_scripts table.
        """
        if not self.inspector or not self.inspector.engine or not script:
            return None
        try:
            with self.inspector.engine.begin() as conn:
                res = conn.execute(
                    text("""
                        INSERT INTO internal.generated_scripts (script, language, task_description, dataset_id, session_id)
                        VALUES (:script, 'sql', :task_description, :dataset_id, :session_id)
                        RETURNING id
                    """),
                    {
                        "script": script,
                        "task_description": sql_description or "PostgreSQL Query Statement",
                        "dataset_id": dataset_id,
                        "session_id": session_id,
                    },
                )
                return res.scalar()
        except Exception as ex:
            logger.error(f"Error saving SQL script to database: {ex}", exc_info=True)
            return None

    def query_database_and_analyze(self, user_input: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyzes database content based on user request, executes query, and returns a structured response with metadata.

        Args:
            user_input (str): Natural language instruction or analytical question.
            session_id (Optional[str]): Optional active session ID.

        Returns:
            Dict[str, Any]: Structured dictionary with response and ID-only metadata.
        """
        final_state = self.run(user_input, session_id=session_id)
        tool_result = final_state.get("tool_result") or {}
        dataset_id = tool_result.get("dataset_id")
        sql_query = final_state.get("sql_query", "")
        table_name = truncate_words(final_state.get("table_name", ""), max_words=5)
        sql_description = truncate_words(final_state.get("sql_description", ""), max_words=5)

        script_id = None
        if sql_query:
            script_id = self._save_sql_script(
                script=sql_query,
                sql_description=sql_description,
                dataset_id=dataset_id,
                session_id=session_id,
            )

        return {
            "response": final_state.get("response", ""),
            "metadata": {
                "dataset_id": dataset_id,
                "script_id": script_id,
                "table_name": table_name,
                "sql_description": sql_description,
            },
        }

    def ingest_file(
        self,
        file_path: Optional[str] = None,
        dataset_name: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingests and validates tabular files (CSV, Excel) into the database.

        Args:
            file_path (Optional[str]): Path to the file on disk.
            dataset_name (Optional[str]): Optional custom dataset name.
            file_bytes (Optional[bytes]): Raw file bytes.
            filename (Optional[str]): Explicit filename override.
            session_id (Optional[str]): Optional session ID to bind this dataset exclusively to a chat session.

        Returns:
            Dict[str, Any]: Ingestion status, metadata, and dataset details or diagnostic error.
        """
        return self.tools.execute(
            "ingest_tabular_file",
            file_path=file_path,
            dataset_name=dataset_name,
            file_bytes=file_bytes,
            filename=filename,
            session_id=session_id,
        )

    def modify_table(self, instruction: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Modifies table data or structure in the session replica database.

        Args:
            instruction (str): Natural language instruction describing the mutation.
            session_id (Optional[str]): Optional active session ID.

        Returns:
            Dict[str, Any]: Status, message, and change record details.
        """
        return self.tools.execute("modify_database_table", instruction=instruction, session_id=session_id)

    def rollback_change(self, session_id: Optional[str] = None, target_change_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Rolls back database changes in the session replica.

        Args:
            session_id (Optional[str]): Active session ID.
            target_change_id (Optional[int]): Optional specific change ID to rollback.

        Returns:
            Dict[str, Any]: Status and description of the rolled back change.
        """
        return self.tools.execute("rollback_database_change", session_id=session_id, target_change_id=target_change_id)

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
        schema_summary = self.inspector.get_schema_summary(session_id=state.get("session_id"))
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

        system_prompt = prompt_loader.render("sql_generation")

        user_content = (
            f"Database Schema:\n{state['schema']}\n\n"
            f"User Request: {state['user_input']}"
            f"{error_context}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]

        sql = ""
        table_name = ""
        sql_description = ""

        try:
            structured_model = self.chat_model.with_structured_output(SQLGenerationOutput)
            result = structured_model.invoke(messages)
            if isinstance(result, dict):
                result = SQLGenerationOutput.model_validate(result)

            if isinstance(result, SQLGenerationOutput):
                sql = result.sql.strip()
                table_name = truncate_words(result.table_name.strip(), max_words=5)
                sql_description = truncate_words(result.sql_description.strip(), max_words=5)
        except Exception as ex:
            logger.warning(f"Structured SQL generation failed ({ex}), falling back to direct invoke")
            try:
                ai_response = self.chat_model.invoke(messages)
                raw_text = extract_text_from_message_content(ai_response.content)
                sql = self._clean_sql_query(raw_text)
            except Exception as fb_err:
                logger.error(f"Fallback invoke failed: {fb_err}")

        if not sql:
            sql = self._clean_sql_query(state.get("sql_query", ""))

        if not table_name:
            user_input = state.get("user_input", "")
            req_words = "".join(c for c in user_input if c.isalnum() or c.isspace()).split()
            table_name = truncate_words(" ".join(req_words[:5]).title() if req_words else "Query Results", max_words=5)
        else:
            table_name = truncate_words(table_name, max_words=5)

        if not sql_description:
            sql_description = truncate_words(f"Query {table_name}", max_words=5)
        else:
            sql_description = truncate_words(sql_description, max_words=5)

        return {
            "sql_query": sql,
            "table_name": table_name,
            "sql_description": sql_description,
        }

    def _execute_sql_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Graph node that executes generated SQL query via ExecuteSQLAndExportCSVTool.

        Args:
            state (AgentState): Current graph state with sql_query.

        Returns:
            Dict[str, Any]: State updates containing tool result and optional error.
        """
        sql_query = state.get("sql_query", "")
        table_name = state.get("table_name", "Query Results")
        tool_result = self.tools.execute(
            "execute_sql_to_csv",
            query=sql_query,
            filename=table_name,
            session_id=state.get("session_id"),
        )

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

        system_prompt = prompt_loader.render("analysis")

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
        """
        cleaned = text.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            for i in range(1, len(parts), 2):
                block = parts[i]
                if block.lower().startswith("sql"):
                    block = block[3:]
                extracted = block.strip()
                if extracted:
                    return extracted
        if cleaned.lower().startswith("sql"):
            cleaned = cleaned[3:].strip()
        return cleaned


def create_db_agent(settings: Optional[Settings] = None) -> DBAgent:
    """
    Constructs and configures DBAgent with database connectivity, tools, and LLM.

    Args:
        settings (Optional[Settings]): Optional custom DB agent settings.

    Returns:
        DBAgent: Initialized DBAgent ready to process database requests.
    """
    cfg = settings or get_settings()

    engine = create_db_engine(cfg.database_url)
    inspector = DatabaseInspector(engine)

    registry = ToolRegistry()
    sql_tool = ExecuteSQLAndExportCSVTool(engine=engine, output_dir=cfg.csv_output_dir)
    registry.register(sql_tool)
    ingest_tool = IngestTabularFileTool(engine=engine)
    registry.register(ingest_tool)

    active_llm = LLMFactory.create(
        provider=cfg.llm_provider,
        api_key=cfg.llm_api_key or None,
        model_name=cfg.llm_model,
    )

    modify_tool = ModifyDatabaseTableTool(engine=engine, llm=active_llm)
    registry.register(modify_tool)
    rollback_tool = RollbackDatabaseChangeTool(engine=engine)
    registry.register(rollback_tool)

    return DBAgent(llm=active_llm, inspector=inspector, tools=registry)


build_agent = create_db_agent

