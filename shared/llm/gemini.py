import os
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from shared.llm.base import BaseLLM, extract_text_from_message_content


class GeminiLLM(BaseLLM):
    """
    Gemini LLM client implementation using LangChain ChatGoogleGenerativeAI.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        resolved_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError("LLM API key must be provided or set in LLM_API_KEY environment variable.")

        self.model_name = model_name or os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
        self.temperature = temperature
        self.chat_model = ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=resolved_key,
            temperature=self.temperature,
            max_retries=6,
        )

    def get_chat_model(self) -> BaseChatModel:
        """
        Retrieves the underlying LangChain ChatGoogleGenerativeAI model.

        Args:
            None

        Returns:
            BaseChatModel: Configured ChatGoogleGenerativeAI instance.
        """
        return self.chat_model

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Generates text completion using the LangChain chat model.

        Args:
            prompt (str): Input prompt for the LLM.
            system_instruction (Optional[str]): System prompt or persona instruction.
            **kwargs (Any): Additional parameters passed to invoke.

        Returns:
            str: Generated text response from Gemini.
        """
        messages: List[BaseMessage] = []
        if system_instruction:
            messages.append(SystemMessage(content=system_instruction))
        messages.append(HumanMessage(content=prompt))

        response = self.chat_model.invoke(messages, **kwargs)
        return extract_text_from_message_content(response.content)

