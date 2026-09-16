from openai import AsyncOpenAI
from app.config import settings

_client = AsyncOpenAI(base_url=settings.embed_base_url, api_key=settings.embed_api_key)


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = await _client.embeddings.create(model=settings.embed_model, input=texts)
    return [d.embedding for d in resp.data]
