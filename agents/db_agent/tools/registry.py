from typing import Any, Dict, List, Optional

from agents.db_agent.tools.base import BaseTool


class ToolRegistry:
    """
    Registry for storing, discovering, and executing agent tools.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Registers a tool instance in the registry.

        Args:
            tool (BaseTool): Tool instance to register.

        Returns:
            None
        """
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """
        Retrieves a registered tool by its name.

        Args:
            name (str): Identifier name of the tool.

        Returns:
            Optional[BaseTool]: The tool instance if registered, None otherwise.
        """
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """
        Retrieves a list of all registered tool instances.

        Args:
            None

        Returns:
            List[BaseTool]: List of registered tools.
        """
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """
        Retrieves schemas and metadata for all registered tools.

        Args:
            None

        Returns:
            List[Dict[str, Any]]: List of dictionary schemas for tools.
        """
        return [tool.to_dict() for tool in self._tools.values()]

    def execute(self, name: str, **kwargs: Any) -> Any:
        """
        Executes a registered tool by name with provided arguments.

        Args:
            name (str): Name of the tool to execute.
            **kwargs (Any): Arguments passed to the tool execution method.

        Returns:
            Any: Result returned by the tool.
        """
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' is not registered.")
        return tool.execute(**kwargs)
