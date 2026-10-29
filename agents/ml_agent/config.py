from functools import lru_cache
import os
from pathlib import Path
import sys
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class MLAgentSettings(BaseSettings):
    """Configuration settings for the Machine Learning Agent and execution environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")

    ml_venv_python: Path = Path(os.getenv("ML_VENV_PYTHON", "/app/.ml_venv/bin/python"))

    execution_timeout_seconds: int = int(os.getenv("ML_EXECUTION_TIMEOUT", "90"))
    max_retries: int = int(os.getenv("ML_MAX_RETRIES", "3"))

    def resolve_python_executable(self) -> str:
        """Resolves the Python executable path for isolated ML code execution."""
        if self.ml_venv_python.exists():
            return str(self.ml_venv_python)

        local_posix = Path("./.ml_venv/bin/python")
        if local_posix.exists():
            return str(local_posix)

        local_win = Path("./.ml_venv/Scripts/python.exe")
        if local_win.exists():
            return str(local_win)

        return sys.executable


@lru_cache(maxsize=1)
def get_ml_settings() -> MLAgentSettings:
    """Retrieves and caches the MLAgentSettings configuration instance."""
    return MLAgentSettings()
