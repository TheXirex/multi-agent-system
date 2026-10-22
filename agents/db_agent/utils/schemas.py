from pydantic import BaseModel, Field


class SQLGenerationOutput(BaseModel):
    """
    Structured schema for PostgreSQL query generation.
    """

    sql: str = Field(
        description="Executable PostgreSQL query addressing the user request."
    )
    table_name: str = Field(
        description="Clean, human-readable title for the resulting dataset (4-5 words maximum, e.g. 'Customer Spending Analysis')."
    )
    sql_description: str = Field(
        description="Concise description explaining what the SQL query accomplishes (4-5 words maximum, e.g. 'Aggregate Customer Order Totals')."
    )
