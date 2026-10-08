import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class MCPServerConfig(BaseModel):
    """
    Configuration specification for an external MCP server process.
    """

    name: str
    command: str = Field(default_factory=lambda: sys.executable)
    args: List[str] = Field(default_factory=lambda: ["-m", "agents.db_agent.mcp_server"])
    env: Optional[Dict[str, str]] = None
    enabled: bool = True


class OrchestratorSettings(BaseSettings):
    """
    Settings configuration for the Orchestrator agent and its MCP client connections.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    csv_output_dir: Path = Path(os.getenv("CSV_OUTPUT_DIR", "./output"))

    # Default configured MCP servers (db_agent included by default; extensible for future agents)
    db_agent_module: str = os.getenv("DB_AGENT_MCP_MODULE", "agents.db_agent.mcp_server")


def get_orchestrator_settings() -> OrchestratorSettings:
    """
    Factory to retrieve cached orchestrator settings.

    Returns:
        OrchestratorSettings: Active settings instance.
    """
    return OrchestratorSettings()
