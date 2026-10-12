import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class MLAgentSettings(BaseSettings):
    """
    Configuration settings for the Machine Learning Agent and execution environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")

    # Path to the dedicated Python executable in .ml_venv
    ml_venv_python: Path = Path(os.getenv("ML_VENV_PYTHON", "/app/.ml_venv/bin/python"))
    output_dir: Path = Path(os.getenv("CSV_OUTPUT_DIR", Path.cwd() / ".cache_temp"))

    execution_timeout_seconds: int = int(os.getenv("ML_EXECUTION_TIMEOUT", "90"))
    max_retries: int = int(os.getenv("ML_MAX_RETRIES", "3"))

    def resolve_python_executable(self) -> str:
        """
        Resolves the python executable path:
        1. Configured ml_venv_python if it exists.
        2. Local .ml_venv if running outside docker.
        3. sys.executable as fallback.
        """
        if self.ml_venv_python.exists():
            return str(self.ml_venv_python)

        # Check local virtual environment in workspace
        local_posix = Path("./.ml_venv/bin/python")
        if local_posix.exists():
            return str(local_posix)

        local_win = Path("./.ml_venv/Scripts/python.exe")
        if local_win.exists():
            return str(local_win)

        return sys.executable


def get_ml_settings() -> MLAgentSettings:
    """
    Retrieves cached or newly loaded MLAgentSettings instance.
    """
    return MLAgentSettings()
