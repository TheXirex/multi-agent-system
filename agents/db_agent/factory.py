from typing import Optional

from agents.db_agent.agent import DBAgent
from agents.db_agent.config import Settings, get_settings
from agents.db_agent.db import DatabaseInspector, create_db_engine
from agents.db_agent.tools import ExecuteSQLAndExportCSVTool, ToolRegistry
from shared.llm import LLMFactory


def build_agent(settings: Optional[Settings] = None) -> DBAgent:
    """
    Constructs and configures the DBAgent instance with database connectivity, tools, and LLM.

    Args:
        settings (Optional[Settings]): Optional custom settings. If None, default settings are loaded.

    Returns:
        DBAgent: Initialized DBAgent ready to process queries.
    """
    cfg = settings or get_settings()

    engine = create_db_engine(cfg.database_url)
    inspector = DatabaseInspector(engine)

    registry = ToolRegistry()
    sql_tool = ExecuteSQLAndExportCSVTool(engine=engine, output_dir=cfg.csv_output_dir)
    registry.register(sql_tool)

    llm = LLMFactory.create(
        provider=cfg.llm_provider,
        api_key=cfg.llm_api_key or None,
        model_name=cfg.llm_model,
    )

    return DBAgent(llm=llm, inspector=inspector, tools=registry)
