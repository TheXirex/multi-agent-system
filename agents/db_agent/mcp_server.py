from typing import Any, Dict, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from agents.db_agent.agent import DBAgent, build_agent


def register_agent_tools(server: MCPServer, agent: DBAgent) -> None:
    """Registers DBAgent capabilities and tools into the provided MCP server instance."""

    @server.tool(
        name="query_and_analyze_database",
        description=(
            "Analyzes database content according to natural language input, generates and executes a SQL query, "
            "persists the SQL script in the database, and returns a structured response containing analysis text and metadata."
        ),
    )
    def query_and_analyze_database(
        user_input: str,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyzes database content and returns a structured response with metadata.

        Args:
            user_input (str): Natural language instruction or analytical question.
            session_id (Optional[str]): Optional active session ID to bind created resources.
            trace_id (Optional[str]): Optional distributed trace ID for unified tracing.
            parent_observation_id (Optional[str]): Optional parent span ID within the trace.

        Returns:
            Dict[str, Any]: Structured dictionary containing response and metadata.
        """
        return agent.query_database_and_analyze(
            user_input,
            session_id=session_id,
            trace_id=trace_id,
            parent_observation_id=parent_observation_id,
        )

    @server.tool(
        name="execute_sql_to_csv",
        description="Executes a raw SQL query statement against the database and returns execution results and preview records.",
    )
    def execute_sql_to_csv(
        query: str,
        filename: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a raw SQL query against the session schema and returns preview records.

        Args:
            query (str): Valid SQL query statement to execute.
            filename (Optional[str]): Optional descriptive title for the query result.
            session_id (Optional[str]): Optional active session ID for replica routing.
            trace_id (Optional[str]): Optional distributed trace ID.
            parent_observation_id (Optional[str]): Optional parent span ID.

        Returns:
            Dict[str, Any]: Execution status, row count, columns, preview records, and metadata.
        """
        result = agent.tools.execute("execute_sql_to_csv", query=query, filename=filename, session_id=session_id)
        return {
            "status": result.get("status"),
            "name": result.get("name"),
            "row_count": result.get("row_count"),
            "columns": result.get("columns"),
            "preview": result.get("preview"),
            "error": result.get("error"),
            "metadata": {
                "table_name": result.get("name"),
                "row_count": result.get("row_count"),
            },
        }

    @server.tool(
        name="get_database_schema",
        description="Retrieves the current PostgreSQL schema information including tables, columns, and foreign keys.",
    )
    def get_database_schema(
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves formatted database schema details for the active session replica.

        Args:
            session_id (Optional[str]): Optional active session ID.
            trace_id (Optional[str]): Optional distributed trace ID.
            parent_observation_id (Optional[str]): Optional parent span ID.

        Returns:
            Dict[str, Any]: Dictionary containing table names, schema summary text, and metadata.
        """
        tables = agent.inspector.get_table_names(session_id=session_id)
        return {
            "tables": tables,
            "schema": agent.inspector.get_schema_summary(session_id=session_id),
            "metadata": {
                "table_names": tables,
            },
        }

    @server.tool(
        name="modify_database_table",
        description=(
            "Modifies database schema or data (INSERT, UPDATE, DELETE rows, ALTER TABLE, CREATE TABLE, DROP TABLE) "
            "in the session replica database. Automatically tracks changes and creates rollback history. "
            "If the request lacks essential information or is ambiguous, asks clarifying questions instead of guessing."
        ),
    )
    def modify_database_table(
        instruction: str,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Modifies database tables or rows in the session database replica.

        Args:
            instruction (str): Natural language description of the requested modification.
            session_id (Optional[str]): Optional active session ID.
            trace_id (Optional[str]): Optional distributed trace ID.
            parent_observation_id (Optional[str]): Optional parent span ID.

        Returns:
            Dict[str, Any]: Structured execution result, change ID, or clarification prompt.
        """
        return agent.modify_table(
            instruction=instruction,
            session_id=session_id,
            trace_id=trace_id,
            parent_observation_id=parent_observation_id,
        )

    @server.tool(
        name="rollback_database_change",
        description=(
            "Reverts the most recent database mutation (or a specific change ID) executed during this session. "
            "Restores previous data or schema state safely using recorded change history."
        ),
    )
    def rollback_database_change(
        session_id: Optional[str] = None,
        target_change_id: Optional[int] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reverts a previous database change in the active session replica.

        Args:
            session_id (Optional[str]): Active session ID whose change history is reverted.
            target_change_id (Optional[int]): Optional specific change history ID to revert.
            trace_id (Optional[str]): Optional distributed trace ID.
            parent_observation_id (Optional[str]): Optional parent span ID.

        Returns:
            Dict[str, Any]: Structured rollback status, reverted change ID, and response message.
        """
        return agent.rollback_change(
            session_id=session_id,
            target_change_id=target_change_id,
            trace_id=trace_id,
            parent_observation_id=parent_observation_id,
        )

    @server.tool(
        name="ingest_tabular_file",
        description=(
            "Ingests, validates, and stores a tabular file (CSV or Excel .xlsx/.xls) as relational tables in the database. "
            "For Excel workbooks with multiple sheets, each sheet is partitioned and stored as an individual table. "
            "Returns table names, column definitions, and summaries, or structured errors if the file is empty, missing, or corrupted."
        ),
    )
    def ingest_tabular_file(
        file_path: str,
        dataset_name: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingests a tabular file from disk into the session PostgreSQL schema.

        Args:
            file_path (str): Filesystem path to the CSV or Excel file.
            dataset_name (Optional[str]): Optional custom target table name.
            session_id (Optional[str]): Optional active session ID.
            trace_id (Optional[str]): Optional distributed trace ID.
            parent_observation_id (Optional[str]): Optional parent span ID.

        Returns:
            Dict[str, Any]: Ingestion status, created table names, column schemas, and preview records.
        """
        return agent.ingest_file(
            file_path=file_path,
            dataset_name=dataset_name,
            session_id=session_id,
            trace_id=trace_id,
            parent_observation_id=parent_observation_id,
        )


def create_mcp_server(agent: Optional[DBAgent] = None) -> MCPServer:
    """Creates and configures an MCP server instance with registered db-agent tools."""
    server = MCPServer("db-agent")
    active_agent = agent or build_agent()
    register_agent_tools(server=server, agent=active_agent)
    return server


def main() -> None:
    """Runs the db-agent MCP server over standard I/O transport."""
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
