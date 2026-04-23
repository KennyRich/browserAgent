from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGENT_")

    provider: Literal["ollama", "openai", "anthropic", "google"] = "ollama"
    model_name: str = "qwen3.5:35b-a3b-coding-nvfp4"

    ollama_base_url: str = "http://localhost:11434/v1"
    use_hosted_model: bool = False
    hosted_ollama_base_url: str = ""
    hosted_ollama_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    headless: bool = False
    max_steps: int = 15
    max_retries: int = 3
    max_concurrent: int = 3
    max_text_length: int = 2000
    max_memory_length: int = 8000
    memory_db_path: str = "memory.db"
    chrome_cdp_url: str = ""
    viewport_width: int = 1280
    viewport_height: int = 720
    log_experiments: bool = False
