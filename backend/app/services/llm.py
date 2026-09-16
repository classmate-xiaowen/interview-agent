import instructor
from openai import AsyncOpenAI
from app.config import settings

_client = instructor.from_openai(
    AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
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
