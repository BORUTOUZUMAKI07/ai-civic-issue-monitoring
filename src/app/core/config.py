from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    API_TOKEN: str = "secret-token"
    
    # MLflow Credentials (optional for the app itself but present in .env)
    MLFLOW_TRACKING_USERNAME: str = ""
    MLFLOW_TRACKING_PASSWORD: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Allow other variables in .env without crashing
    )


settings = Settings()
