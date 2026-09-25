import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "app_db")
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD", "postgres")

    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    csv_output_dir: Path = Path(os.getenv("CSV_OUTPUT_DIR", "./output"))

    @property
    def database_url(self) -> str:
        """
        Builds the database connection URL from individual connection parameters.

        Args:
            None

        Returns:
            str: Formatted PostgreSQL connection URL.
        """
        return f"postgresql+psycopg2://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


def get_settings() -> Settings:
    """
    Retrieves and caches application settings.

    Args:
        None

    Returns:
        Settings: Loaded configuration settings instance.
    """
    return Settings()
