from typing import List, Optional
from pydantic import BaseModel, Field


class ClarityQuestion(BaseModel):
    """
    Schema for a clarification question.
    """

    question: str = Field(description="Specific clarification question.")
    recommended: Optional[str] = Field(
        default=None, description="Recommended default data science option."
    )
    options: List[str] = Field(
        default_factory=list, description="Available candidate options."
    )


class TaskClarityOutput(BaseModel):
    """
    Structured output schema for task clarity assessment.
    """

    needs_clarification: bool = Field(
        description="Whether clarification is strictly required."
    )
    reason: str = Field(description="Concise rationale for clarity decision.")
    questions: List[ClarityQuestion] = Field(
        default_factory=list, description="List of clarification questions."
    )


class MLCodeGenerationOutput(BaseModel):
    """
    Structured output schema for ML Python code generation.
    """

    code_title: str = Field(
        description="Concise, descriptive title for the Python code (4-5 words maximum, e.g. 'Customer Spending Regression Model')."
    )
    code: str = Field(
        description="Complete, executable Python code solving the user task."
    )
