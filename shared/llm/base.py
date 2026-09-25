from abc import ABC, abstractmethod
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel


class BaseLLM(ABC):
    """
    Abstract base interface for LLM client implementations providing LangChain chat model integration.
    """

    @abstractmethod
    def get_chat_model(self) -> BaseChatModel:
        """
        Retrieves the underlying LangChain BaseChatModel instance.

        Args:
            None

        Returns:
            BaseChatModel: Configured LangChain chat model.
        """
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Generates text completion based on the given prompt and optional system instruction.

        Args:
            prompt (str): Input prompt for the LLM.
            system_instruction (Optional[str]): System prompt or persona instruction.
            **kwargs (Any): Additional model configuration parameters.

        Returns:
            str: Generated text response from the model.
        """
        pass


def extract_text_from_message_content(content: Any) -> str:
    """
    Extracts plain text string from LangChain message content (str or list of text blocks).

    Args:
        content (Any): Message content from BaseMessage.

    Returns:
        str: Plain text representation of the message content.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
            elif isinstance(part, str):
                parts.append(part)
            elif hasattr(part, "text"):
                parts.append(str(part.text))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)

