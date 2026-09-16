import app.rag.embedder as emb
import app.rag.store as st
from app.schemas.knowledge import InterviewRecordCreate


def _patch(monkeypatch):
    async def fake_embed(texts):
        return [[0.0] * 8 for _ in texts]
    async def fake_add(chunks):
        return None
    monkeypatch.setattr(emb, "embed", fake_embed)
    monkeypatch.setattr(st, "add_chunks", fake_add)


def test_create_and_list(test_app, monkeypatch):
    _patch(monkeypatch)
    body = InterviewRecordCreate(question="q1", company="Acme",
                                 interviewer_mindset=["deep"]).model_dump()
    r = test_app.post("/api/knowledge/records", json=body)
    assert r.status_code == 200
    rid = r.json()["id"]
    lst = test_app.get("/api/knowledge/records", params={"company": "Acme"})
    assert lst.status_code == 200 and len(lst.json()) >= 1
    d = test_app.delete(f"/api/knowledge/records/{rid}")
    assert d.status_code == 200 and d.json()["deleted"] is True


def test_import(test_app, monkeypatch):
    _patch(monkeypatch)
    items = [InterviewRecordCreate(question=f"q{i}", company="X").model_dump() for i in range(3)]
    r = test_app.post("/api/knowledge/import", json=items)
    assert r.status_code == 200 and r.json()["imported"] == 3
