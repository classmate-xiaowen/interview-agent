import asyncio
import app.rag.embedder as emb


def test_embed_returns_vectors(monkeypatch):
    async def fake_create(*args, **kwargs):
        class D:
            def __init__(self, v):
                self.embedding = v
        class R:
            data = [D([0.1, 0.2]), D([0.3, 0.4])]
        return R()
    monkeypatch.setattr(emb._client.embeddings, "create", fake_create)
    out = asyncio.run(emb.embed(["a", "b"]))
    assert len(out) == 2 and len(out[0]) == 2


def test_embed_empty():
    import app.rag.embedder as e
    async def run():
        return await e.embed([])
    assert asyncio.run(run()) == []
