import logging
from typing import Any, Dict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agents.orchestrator.models import ExecutionPlan, FinalOrchestratorResult, RawExecutionAnswer
from shared.llm.base import BaseLLM, extract_text_from_message_content

logger = logging.getLogger(__name__)

FINALIZER_SYSTEM_PROMPT = """You are the Finalizer in an AI Multi-Agent Orchestrator.
Your goal is to provide a final, well-structured, helpful answer to the user based on raw results returned by domain agents via MCP tools.

Guidelines:
1. Formulate a direct, accurate, and comprehensive answer to the user's initial question.
2. Respond in the same language as the user's question (e.g., if the user asked in Ukrainian, answer in Ukrainian; if in English, answer in English).
3. Clearly summarize the findings, data points, or actions taken.
4. If a CSV table was produced or rows retrieved, mention key numbers/summary points clearly.
5. If any tool call produced an error, explain the issue clearly to the user with constructive guidance.
6. Keep the response natural, clear, and professional.
"""


class Finalizer:
    """
    Synthesizes raw outputs and metadata from tool execution into the final user-facing response.
    """

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm
        self.chat_model: BaseChatModel = llm.get_chat_model()

    def finalize(
        self,
        user_query: str,
        plan: ExecutionPlan,
        raw_answer: RawExecutionAnswer,
    ) -> FinalOrchestratorResult:
        """
        Synthesizes the final answer for the user based on the executed plan and raw results.

        Args:
            user_query (str): The initial user question or requirement.
            plan (ExecutionPlan): The executed plan.
            raw_answer (RawExecutionAnswer): Aggregated outputs and metadata from Executor.

        Returns:
            FinalOrchestratorResult: Structured final response containing text and metadata.
        """
        # If there were no steps (e.g. conversational prompt) or raw_answer already has a clean response
        prompt_content = (
            f"User Question: {user_query}\n\n"
            f"Planner Reasoning: {plan.thought}\n\n"
            f"Raw Tool Outputs:\n{raw_answer.raw_text}\n"
        )

        messages = [
            SystemMessage(content=FINALIZER_SYSTEM_PROMPT),
            HumanMessage(content=prompt_content),
        ]

        try:
            response = self.chat_model.invoke(messages)
            final_text = extract_text_from_message_content(response.content)
        except Exception as exc:
            logger.error(f"Error in Finalizer LLM invocation: {exc}")
            final_text = raw_answer.raw_text or "Execution completed."

        return FinalOrchestratorResult(
            user_query=user_query,
            plan=plan,
            raw_answer=raw_answer,
            final_response=final_text,
            metadata=raw_answer.metadata,
        )
