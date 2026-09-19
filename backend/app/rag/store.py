import asyncio
import chromadb
from app.config import settings
from app.rag import embedder

_COLLECTION_NAME = "interview_chunks"
_client = chromadb.PersistentClient(path=settings.chroma_dir)
_collection = None  # 懒加载，避免导入期阻塞/联网


async def _get_collection():
    """懒加载集合；若已有数据向量维度与当前 OpenAI 模型不符（旧 MiniLM 残留），
    自动删除重建，避免 HNSW 索引维度冲突导致 add/query 报错。"""
    global _collection
    if _collection is not None:
        return _collection
    expected_dim = len((await embedder.embed(["__dim_check__"]))[0])
    col = _client.get_or_create_collection(
        _COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    try:
        if await asyncio.to_thread(col.count) > 0:
            peek = await asyncio.to_thread(
                col.get, limit=1, include=["embeddings"]
            )
            emb = (peek.get("embeddings") or [None])[0]
            if emb is not None and len(emb) != expected_dim:
                _client.delete_collection(_COLLECTION_NAME)
                col = _client.get_or_create_collection(
                    _COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
                )
    except Exception:
        # 维度检查失败时不至于阻断；以当前模型维度为准
        pass
    _collection = col
    return col


async def add_chunks(chunks: list[dict]):
    """chunks: [{id, text, embedding, metadata}]，embedding 由调用方用项目 embedder 预计算。"""
    if not chunks:
        return
    col = await _get_collection()
    await asyncio.to_thread(
        col.add,
        ids=[c["id"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c.get("metadata", {}) for c in chunks],
    )


async def delete_chunks_by_record(record_id: str):
    """删除某个题目对应的全部向量分块，避免删除记录后留下孤儿向量。"""
    if not record_id:
        return
    col = await _get_collection()
    await asyncio.to_thread(col.delete, where={"record_id": record_id})


async def query_chunks(text: str, n: int = 5, filter_meta: dict | None = None) -> list[dict]:
    """用项目 embedder 将 query 编码为向量后做余弦相似检索（不再依赖 Chroma 默认模型）。"""
    if not text or not text.strip():
        return []
    col = await _get_collection()
    vec = (await embedder.embed([text]))[0]
    kwargs = {"query_embeddings": [vec], "n_results": n}
    if filter_meta:
        kwargs["where"] = filter_meta
    res = await asyncio.to_thread(col.query, **kwargs)
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
