import app.rag.embedder as emb
import app.rag.store as st
from app.schemas.knowledge import (
    InterviewRecordCreate, ParsedQuestion, ParsedQuestionBank,
)


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


def _fake_structured(questions):
    async def _fn(system, user, response_model):
        return ParsedQuestionBank(questions=questions)
    return _fn


def test_parse_bank(test_app, monkeypatch):
    monkeypatch.setattr(
        "app.services.knowledge_service.llm.chat_structured",
        _fake_structured([
            ParsedQuestion(question="讲一下最有挑战的项目", my_answer="我当时…", reference_answer="用 STAR 法则"),
            ParsedQuestion(question="", my_answer="应被清洗丢弃"),  # 空题应被丢弃
        ]),
    )
    r = test_app.post("/api/knowledge/parse", json={"text": "一些杂乱的面试笔记"})
    assert r.status_code == 200
    qs = r.json()["questions"]
    assert len(qs) == 1
    assert qs[0]["question"] == "讲一下最有挑战的项目"
    assert qs[0]["my_answer"] == "我当时…"


def test_parse_bank_empty_text(test_app, monkeypatch):
    monkeypatch.setattr(
        "app.services.knowledge_service.llm.chat_structured",
        _fake_structured([]),
    )
    r = test_app.post("/api/knowledge/parse", json={"text": "   "})
    assert r.status_code == 200 and r.json()["questions"] == []
