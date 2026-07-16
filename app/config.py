from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    firebase_credentials_json: str | None = None
    codeword_encryption_key: str
    gemini_api_key: str
    suspicion_confidence_threshold: float = 0.7


settings = Settings()
