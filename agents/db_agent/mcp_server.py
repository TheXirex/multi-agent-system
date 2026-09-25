from typing import Any, Dict, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from agents.db_agent.agent import DBAgent
from agents.db_agent.factory import build_agent


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
            "exports result rows to CSV, and returns a structured response containing analysis text, table metadata, "
            "and SQL code."
        ),
    )
    def query_and_analyze_database(user_input: str) -> Dict[str, Any]:
        """
        Analyzes database content and returns a structured response with metadata.

        Args:
            user_input (str): Natural language instruction or analytical question.

        Returns:
            Dict[str, Any]: Structured dictionary containing response, table metadata (path, rows, cols), and SQL code.
        """
        return agent.query_database_and_analyze(user_input)

    @server.tool(
        name="execute_sql_to_csv",
        description="Executes a raw SQL query statement against the database and exports results to a CSV file.",
    )
    def execute_sql_to_csv(query: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes raw SQL query and exports result to CSV.

        Args:
            query (str): SQL query statement to execute.
            filename (Optional[str]): Optional custom file name for the CSV export.

        Returns:
            Dict[str, Any]: Result status, file path, row count, and column headers.
        """
        return agent.tools.execute("execute_sql_to_csv", query=query, filename=filename)

    @server.tool(
        name="get_database_schema",
        description="Retrieves the current PostgreSQL schema information including tables, columns, and foreign keys.",
    )
    def get_database_schema() -> Dict[str, Any]:
        """
        Retrieves formatted database schema details.

        Args:
            None

        Returns:
            Dict[str, Any]: Dictionary containing schema summary text and list of table names.
        """
        return {
            "tables": agent.inspector.get_table_names(),
            "schema": agent.inspector.get_schema_summary(),
        }


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
