from typing import Any, Dict, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from agents.db_agent.agent import DBAgent, build_agent


def register_agent_tools(server: MCPServer, agent: DBAgent) -> None:
    """
    Registers agent capabilities and tools into the provided MCP server instance.

    Args:
        server (MCPServer): Target MCP server instance.
        agent (DBAgent): DBAgent whose tools and capabilities will be exposed.

    Returns:
        None
    """

    @server.tool(
        name="query_and_analyze_database",
        description=(
            "Analyzes database content according to natural language input, generates and executes SQL query, "
            "saves resulting table with descriptive title in database, persists SQL script in database, "
            "and returns a structured response containing analysis text and metadata."
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
        description="Executes a raw SQL query statement against the database and exports results to a CSV file.",
    )
    def execute_sql_to_csv(
        query: str,
        filename: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes raw SQL query and exports result to CSV.
        """
        result = agent.tools.execute("execute_sql_to_csv", query=query, filename=filename, session_id=session_id)
        return {
            "status": result.get("status"),
            "dataset_id": result.get("dataset_id"),
            "metadata": {
                "dataset_id": result.get("dataset_id"),
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
        Retrieves formatted database schema details.
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
        Reverts previous database change.
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
            "Ingests, validates, and stores a tabular file (CSV or Excel .xlsx/.xls) into the database. "
            "For Excel workbooks with multiple sheets, each sheet is partitioned and stored as an individual dataset. "
            "Returns dataset IDs, column definitions, and summaries, or structured errors if the file is empty, missing, or corrupted."
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
        Ingests a tabular file from disk into PostgreSQL.
        """
        return agent.ingest_file(
            file_path=file_path,
            dataset_name=dataset_name,
            session_id=session_id,
            trace_id=trace_id,
            parent_observation_id=parent_observation_id,
        )


def create_mcp_server(agent: Optional[DBAgent] = None) -> MCPServer:
    """
    Creates and configures an MCP server instance with registered db-agent tools.

    Args:
        agent (Optional[DBAgent]): Configured DBAgent instance. If None, default agent is initialized.

    Returns:
        MCPServer: Configured MCP server instance ready to serve requests.
    """
    server = MCPServer("db-agent")
    active_agent = agent or build_agent()
    register_agent_tools(server=server, agent=active_agent)
    return server


def main() -> None:
    """
    Main entry point for running the db-agent MCP server over standard I/O transport.

    Args:
        None

    Returns:
        None
    """
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
