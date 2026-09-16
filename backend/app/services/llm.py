import instructor
from openai import AsyncOpenAI
from app.config import settings

# DeepSeek 默认开启 thinking 模式，不支持 instructor 默认的 tool_choice；
# 改用 JSON 模式（response_format=json_object）做结构化输出，跨模型更稳。
_client = instructor.from_openai(
    AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key),
    mode=instructor.Mode.JSON,
)


async def chat_structured(system: str, user: str, response_model: type, model: str | None = None):
    return await _client.chat.completions.create(
        model=model or settings.chat_model,
        response_model=response_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
