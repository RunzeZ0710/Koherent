from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://koherent:koherent@localhost:5433/koherent"
    test_database_url: str = "postgresql+psycopg://koherent:koherent@localhost:5433/koherent_test"
    audio_storage_dir: str = "./storage/audio"
    cors_origins: str = "http://localhost:3002"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
