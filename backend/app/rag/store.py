import asyncio
import chromadb
from app.config import settings

_client = chromadb.PersistentClient(path=settings.chroma_dir)
_collection = _client.get_or_create_collection("interview_chunks", metadata={"hnsw:space": "cosine"})


async def add_chunks(chunks: list[dict]):
    if not chunks:
        return
    await asyncio.to_thread(
        _collection.add,
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c.get("metadata", {}) for c in chunks],
    )


async def delete_chunks_by_record(record_id: str):
    """删除某个题目对应的全部向量分块，避免删除记录后留下孤儿向量。"""
    if not record_id:
        return
    await asyncio.to_thread(
        _collection.delete,
        where={"record_id": record_id},
    )


async def query_chunks(text: str, n: int = 5, filter_meta: dict | None = None) -> list[dict]:
    if not text or not text.strip():
        return []
    kwargs = {"query_texts": [text], "n_results": n}
    if filter_meta:
        kwargs["where"] = filter_meta
    res = await asyncio.to_thread(_collection.query, **kwargs)
    out = []
    docs = res.get("documents") or [[]]
    ids = res.get("ids") or [[]]
    metas = res.get("metadatas") or [[]]
    dists = res.get("distances") or [[]]
    for i, doc in enumerate(docs[0]):
        out.append({
            "id": ids[0][i],
            "text": doc,
            "metadata": (metas[0][i] if metas and metas[0] else {}),
            "distance": (dists[0][i] if dists and dists[0] else 0.0),
        })
    return out
