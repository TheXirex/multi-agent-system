from typing import List

from agents.orchestrator.models.schemas import ToolDefinition


def format_tools_description(tools: List[ToolDefinition]) -> str:
    """Formats available MCP tools into a readable schema specification for prompts."""
    if not tools:
        return "No tools currently registered."

    lines = []
    for t in tools:
        schema_params = t.input_schema.get("properties", {})
        required_params = t.input_schema.get("required", [])
        params_str = ", ".join(
            f"{k}: {v.get('type', 'any')}{' (required)' if k in required_params else ''}"
            for k, v in schema_params.items()
        )
        lines.append(f"- '{t.name}' (server: {t.server_name}): {t.description}")
        if params_str:
            lines.append(f"  Arguments: {{{params_str}}}")
    return "\n".join(lines)
