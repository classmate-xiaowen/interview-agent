from __future__ import annotations

import warnings
from pathlib import Path
from typing import ClassVar

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 以本文件位置为基准解析 backend 目录，确保无论从哪个工作目录启动都能正确加载 .env
_BACKEND_DIR = Path(__file__).resolve().parent.parent

# 若 .env 中 API Key 仍是这些值，说明尚未填入真实密钥
_PLACEHOLDER_KEYS = {"YOUR_BAILIAN_API_KEY", "YOUR_OPENAI_API_KEY"}


class Settings(BaseSettings):
    # 全部配置来源于环境变量（backend/.env，已被 gitignore）。
    # 本处 default 仅作兜底/文档，实际运行以 .env 为准（模板见 backend/.env.example）。
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ===== 对话 / Guardrail 大模型（阿里云百炼，OpenAI 兼容模式） =====
    # 百炼控制台获取 API-Key：https://bailian.console.aliyun.com/ → 右上角「API-KEY」
    llm_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="对话/护栏模型 API base_url（OpenAI 兼容协议）",
    )
    llm_api_key: str = Field(
        default="YOUR_BAILIAN_API_KEY",
        description="百炼 API-Key；占位符需在 backend/.env 中替换为真实密钥",
    )
    chat_model: str = Field(default="qwen-plus", description="对话/点评模型；可选 qwen-max / qwen-turbo / qwen-long 等")
    guardrail_model: str = Field(default="qwen-plus", description="护栏（轻量判定）模型")
    llm_provider: str = Field(
        default="bailian",
        description="bailian / deepseek，决定结构化/流式调用是否下发思考链参数（仅 DeepSeek 需要）",
    )

    # ===== 向量 Embedding =====
    # 百炼亦提供 text-embedding-v3，可改用百炼能力（base_url/api_key 同百炼）
    embed_base_url: str = Field(default="https://api.openai.com/v1", description="Embedding API base_url")
    embed_api_key: str = Field(default="", description="Embedding API-Key")
    embed_model: str = Field(default="text-embedding-3-small", description="Embedding 模型名")

    # ===== 其它 =====
    chroma_dir: str = Field(default="./chroma_data", description="Chroma 向量库持久化目录")
    db_path: str = Field(
        default="sqlite+aiosqlite:///./speak_agent.db",
        description="SQLite 元数据数据库连接串",
    )
    max_questions: int = Field(default=12, description="单场面试默认题目数量上限（可被每场 InterviewConfig.max_questions 覆盖）")
    llm_max_tokens: int = Field(default=8192, description="结构化输出（InterviewTurn 评估）token 上限，避免长评估 JSON 被截断")
    llm_disable_thinking: bool = Field(
        default=True,
        description="结构化/流式调用时关闭模型思考链（仅 DeepSeek 生效；百炼 qwen 不识别该参数）",
    )

    @model_validator(mode="after")
    def _validate_config(self) -> Settings:
        for name in ("llm_api_key", "embed_api_key"):
            if getattr(self, name) in _PLACEHOLDER_KEYS:
                warnings.warn(
                    f"配置项 {name} 仍是占位符（{getattr(self, name)}），请在 backend/.env 中填入真实密钥，否则相关 LLM / Embedding 调用会失败。",
                    stacklevel=2,
                )
        if self.llm_provider not in ("bailian", "deepseek"):
            warnings.warn(
                f"llm_provider={self.llm_provider!r} 不是预期值（bailian / deepseek），思考链参数逻辑可能不符合预期。",
                stacklevel=2,
            )
        return self


settings = Settings()
