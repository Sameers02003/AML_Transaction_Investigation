from pydantic_settings import BaseSettings # type: ignore

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://aml:aml@localhost:5432/aml"
    kafka_bootstrap: str = "localhost:9092"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    ingest_api_key: str = "dev-ingest-key"
    ingest_mode: str = "sync"          # sync | kafka
    alert_threshold: float = 0.5
    model_config = {"env_file": ".env"}

settings = Settings()