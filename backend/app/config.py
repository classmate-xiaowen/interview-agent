from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    # 对话 / Guardrail 大模型（DeepSeek 兼容 OpenAI 协议）
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    chat_model: str = "v4flash"
    guardrail_model: str = "v4flash"
    # 向量 Embedding（DeepSeek 不提供 embedding，默认走 OpenAI；可换成任意兼容服务）
    embed_base_url: str = "https://api.openai.com/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-small"
    chroma_dir: str = "./chroma_data"
    db_path: str = "sqlite+aiosqlite:///./speak_agent.db"
    max_questions: int = 5


settings = Settings()
