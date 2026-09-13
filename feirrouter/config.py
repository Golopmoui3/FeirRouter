"""Central settings. Union of env conventions from all three routers."""
from __future__ import annotations
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    FEIR_HOST: str = "127.0.0.1"
    FEIR_PORT: int = 8081
    FEIR_UNIFIED_KEY: str = ""
    FEIR_MASTER_KEY: str = "change-me-32-chars-minimum!!!"
    FEIR_DB_PATH: str = "./data/feir.db"
    FEIR_STRATEGY: str = "auto"
    FEIR_MAX_ATTEMPTS: int = 20
    FEIR_TIMEOUT: float = 300.0
    FEIR_CONCURRENCY: int = 8
    FEIR_COMPRESSION: bool = True
    FEIR_PROBES: bool = True

    # per-tier routing (FCC idea)
    MODEL: str = "nvidia_nim/stepfun-ai/step-3.5-flash"
    MODEL_OPUS: str = ""
    MODEL_SONNET: str = ""
    MODEL_HAIKU: str = ""
    MODEL_FABLE: str = ""

    LM_STUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LLAMACPP_BASE_URL: str = "http://localhost:8080/v1"
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"


settings = Settings()


def provider_env(prefix: str) -> dict:
    """Collect PROVIDER env: <PREFIX>_API_KEY, <PREFIX>_BASE_URL, ..."""
    out: dict = {}
    p = prefix.upper()
    for k, v in os.environ.items():
        if k.startswith(p + "_") and v:
            out[k] = v
    # also pydantic-populated values already in env
    return out
