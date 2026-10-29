import logging
import os
from typing import Any, List, Optional
import warnings

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from shared.llm.base import BaseLLM, extract_text_from_message_content

logging.getLogger("google_genai.models").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_google_genai")


class GeminiLLM(BaseLLM):
    """Gemini LLM client implementation using LangChain ChatGoogleGenerativeAI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        """Initializes the Gemini LLM client wrapper."""
        resolved_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError("LLM API key must be provided or set in LLM_API_KEY environment variable.")

        self.model_name = model_name or os.getenv("LLM_MODEL", "gemini-3.8-flash")
        self.temperature = temperature
        self.chat_model = ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=resolved_key,
            temperature=self.temperature,
            max_retries=6,
        )

    def get_chat_model(self) -> BaseChatModel:
        """Retrieves the underlying LangChain ChatGoogleGenerativeAI model."""
        return self.chat_model

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Generates text completion using the LangChain chat model."""
        messages: List[BaseMessage] = []
        if system_instruction:
            messages.append(SystemMessage(content=system_instruction))
        messages.append(HumanMessage(content=prompt))

        response = self.chat_model.invoke(messages, **kwargs)
        return extract_text_from_message_content(response.content)
