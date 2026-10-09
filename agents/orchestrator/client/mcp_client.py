import json
import logging
import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agents.orchestrator.config import MCPServerConfig
from agents.orchestrator.models import StepExecutionResult, ToolDefinition

logger = logging.getLogger(__name__)


class MCPClientManager:
    """
    Manager for MCP client sessions that discovers tools from registered MCP servers,
    routes tool invocations, and handles responses and metadata.
    """

    def __init__(self, servers: Optional[Dict[str, MCPServerConfig]] = None) -> None:
        self.server_configs: Dict[str, MCPServerConfig] = {}
        self._tool_to_server_map: Dict[str, str] = {}
        self._cached_tools: Dict[str, ToolDefinition] = {}

        # Register default db_agent server
        self.register_server(
            MCPServerConfig(
                name="db_agent",
                command=sys.executable,
                args=["-m", "agents.db_agent.mcp_server"],
                env=dict(os.environ),
                enabled=True,
            )
        )

        if servers:
            for s_name, s_cfg in servers.items():
                self.register_server(s_cfg)

    def register_server(self, config: MCPServerConfig) -> None:
        """
        Registers an MCP server configuration.

        Args:
            config (MCPServerConfig): Server configuration details.
        """
        self.server_configs[config.name] = config

    @asynccontextmanager
    async def open_session(self) -> AsyncGenerator["ActiveMCPSession", None]:
        """
        Context manager that establishes active MCP sessions with all enabled servers.
        Guarantees clean shutdown of subprocesses upon exit.

        Yields:
            ActiveMCPSession: Active session wrapper ready to list and call tools.
        """
        async with AsyncExitStack() as stack:
            sessions: Dict[str, ClientSession] = {}

            for server_name, cfg in self.server_configs.items():
                if not cfg.enabled:
                    continue

                server_env = dict(os.environ)
                if cfg.env:
                    server_env.update(cfg.env)

                params = StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args,
                    env=server_env,
                )

                read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()
                sessions[server_name] = session

            active = ActiveMCPSession(sessions=sessions)
            await active.discover_tools()
            yield active


class ActiveMCPSession:
    """
    Active multi-server MCP session wrapper for discovery and invocation.
    """

    def __init__(self, sessions: Dict[str, ClientSession]) -> None:
        self.sessions: Dict[str, ClientSession] = sessions
        self.tool_map: Dict[str, ToolDefinition] = {}
        self.tool_to_server: Dict[str, str] = {}

    async def discover_tools(self) -> List[ToolDefinition]:
        """
        Discovers tools across all active MCP server sessions.

        Returns:
            List[ToolDefinition]: Aggregated list of available tools.
        """
        self.tool_map.clear()
        self.tool_to_server.clear()

        for server_name, session in self.sessions.items():
            try:
                res = await session.list_tools()
                for tool in res.tools:
                    defn = ToolDefinition(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=tool.input_schema if hasattr(tool, "input_schema") else {},
                        server_name=server_name,
                    )
                    self.tool_map[tool.name] = defn
                    self.tool_to_server[tool.name] = server_name
            except Exception as e:
                logger.error(f"Error discovering tools from server {server_name}: {e}")

        return list(self.tool_map.values())

    async def list_tools(self) -> List[ToolDefinition]:
        """
        Returns cached list of tools or triggers discovery.

        Returns:
            List[ToolDefinition]: List of tool definitions.
        """
        if not self.tool_map:
            return await self.discover_tools()
        return list(self.tool_map.values())

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """
        Discovers available prompt templates across all active MCP servers.

        Returns:
            List[Dict[str, Any]]: Aggregated list of available prompts.
        """
        prompts = []
        for server_name, session in self.sessions.items():
            try:
                res = await session.list_prompts()
                for p in getattr(res, "prompts", []):
                    prompts.append({
                        "name": getattr(p, "name", ""),
                        "description": getattr(p, "description", ""),
                        "server_name": server_name,
                    })
            except Exception as e:
                logger.debug(f"Server {server_name} does not provide prompts or failed: {e}")
        return prompts

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        step_id: int = 1,
    ) -> StepExecutionResult:
        """
        Routes and executes a tool call on the appropriate MCP server.

        Args:
            tool_name (str): Tool identifier to execute.
            arguments (Dict[str, Any]): Arguments passed to the tool.
            step_id (int): Identifier of the plan step.

        Returns:
            StepExecutionResult: Standardized execution result containing raw output and metadata.
        """
        server_name = self.tool_to_server.get(tool_name)
        if not server_name or server_name not in self.sessions:
            return StepExecutionResult(
                step_id=step_id,
                tool_name=tool_name,
                arguments=arguments,
                raw_content=None,
                success=False,
                error=f"Tool '{tool_name}' not found on any active MCP server.",
            )

        session = self.sessions[server_name]
        try:
            call_res = await session.call_tool(tool_name, arguments=arguments)
            raw_text_parts: List[str] = []
            parsed_data: Optional[Dict[str, Any]] = None
            metadata: Dict[str, Any] = {}

            for content in call_res.content:
                if hasattr(content, "text"):
                    text_val = content.text
                    raw_text_parts.append(text_val)

                    # Try parsing JSON if structured
                    try:
                        parsed = json.loads(text_val)
                        if isinstance(parsed, dict):
                            parsed_data = parsed

                            # Extract metadata if provided
                            if "metadata" in parsed and isinstance(parsed["metadata"], dict):
                                metadata.update(parsed["metadata"])

                            # Extract table metadata directly if present at root
                            if "file_path" in parsed or "columns" in parsed:
                                table_meta = metadata.get("table", {})
                                table_meta.setdefault("file_path", parsed.get("file_path", ""))
                                table_meta.setdefault("file_name", parsed.get("file_name", ""))
                                table_meta.setdefault("row_count", parsed.get("row_count", 0))
                                table_meta.setdefault("columns", parsed.get("columns", []))
                                table_meta.setdefault("preview", parsed.get("preview", []))
                                metadata["table"] = table_meta

                            if "sql_query" in parsed or "query" in parsed:
                                code_meta = metadata.get("code", {})
                                code_meta.setdefault("language", "sql")
                                code_meta.setdefault("query", parsed.get("sql_query") or parsed.get("query"))
                                metadata["code"] = code_meta

                    except (json.JSONDecodeError, TypeError):
                        pass

            raw_combined = "\n".join(raw_text_parts)

            return StepExecutionResult(
                step_id=step_id,
                tool_name=tool_name,
                arguments=arguments,
                raw_content=raw_combined,
                structured_data=parsed_data,
                metadata=metadata,
                success=True,
                error=None,
            )

        except Exception as exc:
            logger.error(f"Error calling MCP tool {tool_name}: {exc}", exc_info=True)
            return StepExecutionResult(
                step_id=step_id,
                tool_name=tool_name,
                arguments=arguments,
                raw_content=None,
                success=False,
                error=str(exc),
            )
