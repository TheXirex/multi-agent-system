import logging
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from agents.ml_agent.agent import MLAgent, build_ml_agent

logger = logging.getLogger(__name__)


def register_agent_tools(server: MCPServer, agent: MLAgent) -> None:
    """Registers ML Agent tools into the provided MCP server instance."""

    @server.tool(
        name="run_ml_analysis",
        description=(
            "Performs machine learning modeling, predictive analytics, statistical analysis, "
            "or data visualization on given in-memory dataset(s) or database table(s). "
            "Formulates Python code using in-memory data copies (e.g. df = data.copy()), executes it in an isolated ML environment, "
            "repairs runtime errors automatically, persists interactive Plotly charts and scripts in the database, "
            "and returns analytical findings with ID-only metadata."
        ),
    )
    async def run_ml_analysis(
        task_description: str,
        dataset_path: Optional[str] = None,
        dataset_id: Optional[int] = None,
        dataset_ids: Optional[List[int]] = None,
        table_names: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        sql_query: Optional[str] = None,
        trace_id: Optional[str] = None,
        parent_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes an ML or visualization task on the given dataset(s) or database table(s).

        Args:
            task_description (str): Natural language description of the analytical or ML task.
            dataset_path (Optional[str]): Optional path to tabular dataset file on disk.
            dataset_id (Optional[int]): Database identifier of the primary dataset.
            dataset_ids (Optional[List[int]]): Optional list of multiple dataset identifiers.
            table_names (Optional[List[str]]): Relational database table name or list of table names to analyze.
            session_id (Optional[str]): Optional session ID to bind and scope the analysis.
            sql_query (Optional[str]): Optional SQL query string associated with data preparation.
            trace_id (Optional[str]): Optional distributed trace ID for unified tracing.
            parent_observation_id (Optional[str]): Optional parent span ID within the trace.

        Returns:
            Dict[str, Any]: Structured dictionary with response text and ID-only metadata.
        """
        return await agent.run(
            task_description=task_description,
            dataset_path=dataset_path,
            dataset_id=dataset_id,
            dataset_ids=dataset_ids,
            table_names=table_names,
            session_id=session_id,
            sql_query=sql_query,
            trace_id=trace_id,
            parent_observation_id=parent_observation_id,
        )


def create_ml_mcp_server(agent: Optional[MLAgent] = None) -> MCPServer:
    """Creates and initializes the MCP server exposing ML Agent tools."""
    server = MCPServer("ml_agent")
    active_agent = agent or build_ml_agent()
    register_agent_tools(server, active_agent)
    return server


def main() -> None:
    """Runs the ml_agent MCP server over standard I/O transport."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("Starting ML Agent MCP Server...")
    mcp_app = create_ml_mcp_server()
    mcp_app.run(transport="stdio")


if __name__ == "__main__":
    main()
