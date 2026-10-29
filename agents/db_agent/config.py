from functools import lru_cache
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

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "app_db"
    db_user: str = "postgres"
    db_password: str = "postgres"

    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    llm_api_key: str = ""
    csv_output_dir: Path = Path(".cache_temp")

    @property
    def database_url(self) -> str:
        """
        Builds the database connection URL from individual connection parameters.

        Returns:
            str: Formatted PostgreSQL connection URL.
        """
        return f"postgresql+psycopg2://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Retrieves and caches application settings.

    Returns:
        Settings: Loaded configuration settings instance.
    """
    return Settings()
