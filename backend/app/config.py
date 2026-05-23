from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    upload_dir: str = "uploads"
    storage_dir: str = "storage"
    database_url: str = "sqlite:///./course_agent.db"
    default_report_mode: str = "standard"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    llm_timeout_seconds: float = 120.0

    quick_text_provider: str = "deepseek"
    quick_text_model: str = "DeepSeek-V3.2"
    standard_text_provider: str = "deepseek"
    standard_text_model: str = "DeepSeek-V3.2"
    visual_text_provider: str = "deepseek"
    visual_text_model: str = "DeepSeek-V3.2"
    visual_vision_provider: str = "kimi"
    visual_vision_model: str = "Kimi-K2.5"
    advanced_provider: str = "kimi"
    advanced_model: str = "Kimi-K2.5"
    review_provider: str = "glm"
    review_model: str = "GLM-4.7"
    chat_provider: str = "deepseek"
    chat_model: str = "DeepSeek-V3.2"
    advanced_chat_provider: str = "gemini"
    advanced_chat_model: str = "gemini-2.5-pro"
    page_judge_provider: str = "kimi"
    page_judge_model: str = "Kimi-K2.5"

    openai_compatible_api_key: str = ""
    openai_compatible_base_url: str = "https://modelservice.jdcloud.com/coding/openai/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://modelservice.jdcloud.com/coding/anthropic"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://modelservice.jdcloud.com/coding/openai/v1"
    glm_api_key: str = ""
    glm_base_url: str = "https://modelservice.jdcloud.com/coding/openai/v1"
    kimi_api_key: str = ""
    kimi_base_url: str = "https://modelservice.jdcloud.com/coding/openai/v1"
    gemini_api_key: str = ""
    gemini_base_url: str = "https://modelservice.jdcloud.com/coding/openai/v1"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://modelservice.jdcloud.com/coding/openai/v1"

    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8")


settings = Settings()


def resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()
