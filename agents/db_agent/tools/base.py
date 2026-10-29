from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """Abstract base class defining the contract for all agent tools."""

    name: str
    description: str
    parameters_schema: Dict[str, Any]

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Executes the tool with the provided keyword arguments."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serializes tool metadata and parameter schema to a dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
        }
