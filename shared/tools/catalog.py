from typing import Dict, Optional

# Generalized catalog of MCP tools, short action labels for live execution, and descriptions
TOOL_ACTION_CATALOG: Dict[str, Dict[str, str]] = {
    "get_database_schema": {
        "label": "Inspecting database structure...",
        "description": "Retrieves database schema, tables, columns, constraints, and relationships.",
    },
    "query_and_analyze_database": {
        "label": "Querying database records...",
        "description": "Executes analytical SQL queries and calculates statistical metrics.",
    },
    "modify_database_table": {
        "label": "Updating database...",
        "description": "Executes table modifications, records mutations, and logs rollback history.",
    },
    "rollback_database_change": {
        "label": "Reverting database changes...",
        "description": "Undoes previous schema and data mutations using change history.",
    },
    "ingest_tabular_file": {
        "label": "Ingesting dataset...",
        "description": "Parses CSV or Excel files and provisions dedicated relational tables.",
    },
    "execute_sql_to_csv": {
        "label": "Executing SQL query...",
        "description": "Executes a raw SQL query against the database and retrieves resulting records.",
    },
    "run_ml_analysis": {
        "label": "Analyzing data & generating insights...",
        "description": "Performs data analysis, statistical modeling, visualizations, and machine learning.",
    },
}

DEFAULT_ACTION_LABEL = "Executing step..."


def get_tool_action_label(tool_name: str, fallback: Optional[str] = None) -> str:
    """Returns the concise user-facing action label for a given tool."""
    tool_info = TOOL_ACTION_CATALOG.get(tool_name)
    if tool_info and "label" in tool_info:
        return tool_info["label"]
    return fallback or DEFAULT_ACTION_LABEL


def get_tool_description(tool_name: str, fallback: Optional[str] = None) -> str:
    """Returns the short human-readable description for a given tool."""
    tool_info = TOOL_ACTION_CATALOG.get(tool_name)
    if tool_info and "description" in tool_info:
        return tool_info["description"]
    return fallback or ""
