from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://koherent:koherent@localhost:5433/koherent"
    test_database_url: str = "postgresql+psycopg://koherent:koherent@localhost:5433/koherent_test"
    audio_storage_dir: str = "./storage/audio"
    cors_origins: str = "http://localhost:3002"
    nvidia_api_key: str | None = None
    # Calibrated against real nv-embedqa-e5-v5 output: on-topic notes score
    # ~0.54-0.67, off-topic ~0.37, so 0.45 separates them. Tunable starting point.
    anomaly_threshold: float = 0.45
    nim_chat_model: str = "meta/llama-3.3-70b-instruct"
    # Character cap on assembled retrieval context before an LLM call; keeps
    # prompts well inside the model window without token-counting machinery.
    context_char_budget: int = 12000
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
