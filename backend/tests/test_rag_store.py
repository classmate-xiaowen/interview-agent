import pytest
import uuid
import app.rag.chunker as ch
import app.rag.store as st


def test_chunk_text_splits_long():
    text = "段落一。" * 300 + "\n\n段落二。" * 300
    parts = ch.chunk_text(text, max_chars=400, overlap=40)
    assert len(parts) >= 2
    assert all(len(p) <= 480 for p in parts)


def test_chunk_text_empty():
    assert ch.chunk_text("") == []
    assert ch.chunk_text("   \n  ") == []


@pytest.mark.asyncio
async def test_add_and_query():
    uid = uuid.uuid4().hex
    chunks = [{"id": f"c-{uid}", "text": "RAG 结合检索与生成", "metadata": {"company": "Acme"}}]
    await st.add_chunks(chunks)
    res = await st.query_chunks("RAG 检索", n=3, filter_meta={"company": "Acme"})
    assert any(r["id"] == f"c-{uid}" for r in res)


@pytest.mark.asyncio
async def test_query_empty():
    assert await st.query_chunks("", n=3) == []
