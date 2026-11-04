from typing import Optional
from pydantic import BaseModel, Field


class SQLGenerationOutput(BaseModel):
    """Structured schema for PostgreSQL query generation and schema validation."""

    is_possible: bool = Field(
        default=True,
        description="Whether the user request can be fulfilled with the schema. Set to false if a requested column or table does not exist in the database.",
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Clear explanation if the request cannot be fulfilled (e.g. 'The requested table does not contain column <col>; available columns are: ...').",
    )
    sql: str = Field(
        default="",
        description="Executable PostgreSQL query addressing the user request. Leave empty if is_possible is false.",
    )
    table_name: str = Field(
        default="Query Results",
        description="Clean, human-readable title for the resulting dataset (4-5 words maximum, e.g. 'Customer Spending Analysis').",
    )
    sql_description: str = Field(
        default="",
        description="Concise description explaining what the SQL query accomplishes (4-5 words maximum, e.g. 'Aggregate Customer Order Totals').",
    )
