import voyageai

from app.core.config import settings

_client = voyageai.AsyncClient(api_key=settings.voyage_api_key)


async def embed(text: str) -> list[float]:
    response = await _client.embed(texts=[text], model="voyage-3")
    return response.embeddings[0]
