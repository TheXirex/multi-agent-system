from typing import Optional

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.config import OrchestratorSettings, get_orchestrator_settings
from agents.orchestrator.mcp_client import MCPClientManager
from shared.llm.base import BaseLLM
from shared.llm.factory import LLMFactory


def build_orchestrator(
    settings: Optional[OrchestratorSettings] = None,
    llm: Optional[BaseLLM] = None,
    mcp_manager: Optional[MCPClientManager] = None,
) -> OrchestratorAgent:
    """
    Factory function to construct a fully configured OrchestratorAgent.

    Args:
        settings (Optional[OrchestratorSettings]): Custom settings instance.
        llm (Optional[BaseLLM]): Pre-configured LLM instance.
        mcp_manager (Optional[MCPClientManager]): Custom MCP client manager.

    Returns:
        OrchestratorAgent: Initialized orchestrator agent.
    """
    cfg = settings or get_orchestrator_settings()

    active_llm = llm or LLMFactory.create(
        provider=cfg.llm_provider,
        model_name=cfg.llm_model,
        api_key=cfg.llm_api_key,
    )

    manager = mcp_manager or MCPClientManager()

    return OrchestratorAgent(
        llm=active_llm,
        mcp_manager=manager,
    )
