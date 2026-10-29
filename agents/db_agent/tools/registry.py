from typing import Any, Dict, List, Optional

from agents.db_agent.tools.base import BaseTool


class ToolRegistry:
    """Registry for storing, discovering, and executing agent tools."""

    def __init__(self) -> None:
        """Initializes an empty tool registry."""
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registers a tool instance in the registry."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieves a registered tool by its name."""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """Retrieves a list of all registered tool instances."""
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Retrieves schemas and metadata for all registered tools."""
        return [tool.to_dict() for tool in self._tools.values()]

    def execute(self, name: str, **kwargs: Any) -> Any:
        """Executes a registered tool by name with the provided arguments."""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' is not registered.")
        return tool.execute(**kwargs)
