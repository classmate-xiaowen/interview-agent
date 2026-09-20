from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    # 对话 / Guardrail 大模型（DeepSeek 兼容 OpenAI 协议）
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    chat_model: str = "deepseek-flash"
    guardrail_model: str = "deepseek-flash"
    # 向量 Embedding（DeepSeek 不提供 embedding，默认走 OpenAI；可换成任意兼容服务）
    embed_base_url: str = "https://api.openai.com/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-small"
    chroma_dir: str = "./chroma_data"
    db_path: str = "sqlite+aiosqlite:///./speak_agent.db"
    max_questions: int = 12  # 单场面试默认题目数量上限（可被每场 InterviewConfig.max_questions 覆盖）
    llm_max_tokens: int = 8192  # 结构化输出（InterviewTurn 评估）的 token 上限，避免长评估 JSON 被截断
    llm_disable_thinking: bool = True  # 结构化/流式调用时关闭模型思考链（DeepSeek 默认开启会吃掉 JSON 预算导致截断）


settings = Settings()
