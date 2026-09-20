import asyncio
import chromadb
from app.config import settings
from app.rag import embedder

_COLLECTION_NAME = "interview_chunks"
_client = chromadb.PersistentClient(path=settings.chroma_dir)
_collection = None  # 懒加载，避免导入期阻塞/联网


def _create_collection():
    return _client.get_or_create_collection(
        _COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


async def reset_collection() -> None:
    """删除并重建向量集合（用于维度变更 / 旧数据清理）。"""
    global _collection
    try:
        _client.delete_collection(_COLLECTION_NAME)
    except Exception as e:
        print(f"[store] delete_collection 失败（可忽略，可能本就不存在）: {e}")
    _collection = _create_collection()


async def check_dimension_mismatch() -> bool:
    """当前 embedding 模型维度与已有集合不符则返回 True（含：无数据/无法判断均按 False/True 处理）。"""
    try:
        expected_dim = len((await embedder.embed(["__dim_check__"]))[0])
    except Exception as e:
        print(f"[store] 探测 embedding 维度失败，跳过维度自愈: {e}")
        return False
    try:
        col = _client.get_collection(_COLLECTION_NAME)
    except Exception:
        return False
    try:
        if await asyncio.to_thread(col.count) == 0:
            return False
        peek = await asyncio.to_thread(col.get, limit=1, include=["embeddings"])
        embs = peek.get("embeddings")
        emb = None if embs is None or len(embs) == 0 else embs[0]
        return emb is None or len(emb) != expected_dim
    except Exception as e:
        # 无法判断维度时保守认为需要重建，避免后续 add/query 维度冲突
        print(f"[store] 维度探测异常，保守判定需重建集合: {e}")
        return True


async def _get_collection():
    """懒加载集合；若已有数据向量维度与当前 embedding 模型不符（旧 MiniLM 残留），
    自动删除重建，避免 HNSW 索引维度冲突导致 add/query 报错。"""
    global _collection
    if _collection is not None:
        return _collection
    if await check_dimension_mismatch():
        await reset_collection()
        return _collection
    _collection = _create_collection()
    return _collection


async def add_chunks(chunks: list[dict]):
    """chunks: [{id, text, embedding, metadata}]，embedding 由调用方用项目 embedder 预计算。"""
    if not chunks:
        return
    col = await _get_collection()
    kwargs = dict(
        ids=[c["id"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c.get("metadata", {}) for c in chunks],
    )
    try:
        await asyncio.to_thread(col.add, **kwargs)
    except Exception as e:
        if "dimension" in str(e).lower():
            # 维度冲突兜底：重建集合后重试一次（数据由调用方负责重新索引）
            await reset_collection()
            await asyncio.to_thread(_collection.add, **kwargs)
        else:
            raise


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
    try:
        res = await asyncio.to_thread(col.query, **kwargs)
    except Exception as e:
        if "dimension" in str(e).lower():
            # 维度冲突兜底：重建集合后重试一次（重建后集合为空，返回空结果而非报错）
            await reset_collection()
            res = await asyncio.to_thread(_collection.query, **kwargs)
        else:
            raise
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
