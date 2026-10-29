from typing import Any, Dict, Type

from shared.llm.base import BaseLLM
from shared.llm.gemini import GeminiLLM


class LLMFactory:
    """Factory for creating and managing LLM client instances."""

    _registry: Dict[str, Type[BaseLLM]] = {
        "gemini": GeminiLLM,
    }

    @classmethod
    def register(cls, provider: str, llm_class: Type[BaseLLM]) -> None:
        """Registers a new LLM provider implementation."""
        cls._registry[provider.lower()] = llm_class

    @classmethod
    def create(cls, provider: str = "gemini", **kwargs: Any) -> BaseLLM:
        """Creates and returns an LLM client instance for the specified provider."""
        provider_key = provider.lower()
        llm_class = cls._registry.get(provider_key)
        if not llm_class:
            available = ", ".join(cls._registry.keys())
            raise ValueError(f"Unsupported LLM provider '{provider}'. Available providers: {available}")

        return llm_class(**kwargs)

    @classmethod
    def create_chat_model(cls, provider: str = "gemini", **kwargs: Any) -> Any:
        """Creates and returns a LangChain chat model instance for the specified provider."""
        instance = cls.create(provider=provider, **kwargs)
        return instance.get_chat_model()
