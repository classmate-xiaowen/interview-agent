import instructor
from typing import AsyncIterator
from openai import AsyncOpenAI
from app.config import settings

# DeepSeek 默认开启 thinking 模式，不支持 instructor 默认的 tool_choice；
# 改用 JSON 模式（response_format=json_object）做结构化输出，跨模型更稳。
_client = instructor.from_openai(
    AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key),
    mode=instructor.Mode.JSON,
)

# 流式输出（逐 token 返回）使用原生 OpenAI 客户端，避免 instructor 的 JSON 解码层。
_raw_client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


async def chat_structured(system: str, user: str, response_model: type, model: str | None = None, history: list[dict] | None = None):
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})
    return await _client.chat.completions.create(
        model=model or settings.chat_model,
        response_model=response_model,
        messages=messages,
    )


async def stream_text(system: str, user: str, model: str | None = None, history: list[dict] | None = None) -> AsyncIterator[str]:
    """流式生成纯文本（面试问题 / 总结），逐 chunk 返回，供 SSE 推送。"""
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})
    stream = await _raw_client.chat.completions.create(
        model=model or settings.chat_model,
        messages=messages,
        stream=True,
        temperature=0.7,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
