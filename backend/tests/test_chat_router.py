import app.services.interview_harness as h
import app.services.llm as llm
from app.schemas.interview import InterviewTurn, Evaluation


def _mock(monkeypatch):
    async def fake_llm(system, user, response_model, model=None):
        if "EVAL" in user:
            return InterviewTurn(question="下一题", question_type="technical",
                                evaluation=Evaluation(score=75))
        return InterviewTurn(question="请做自我介绍", question_type="behavioral")
    monkeypatch.setattr(llm, "chat_structured", fake_llm)
    async def fake_query(*a, **k):
        return []
    monkeypatch.setattr(h.store, "query_chunks", fake_query)


def test_session_and_message_sse(test_app, monkeypatch):
    _mock(monkeypatch)
    s = test_app.post("/api/chat/session", json={"interviewer_style": "gentle"})
    assert s.status_code == 200
    assert s.json()["session_id"]
    sid = s.json()["session_id"]
    with test_app.stream("POST", "/api/chat/message",
                         json={"session_id": sid, "message": "我的回答"}) as r:
        body = "".join(line for line in r.iter_lines())
    assert "event: turn" in body
    assert "question" in body


def test_unknown_session(test_app):
    r = test_app.post("/api/chat/message",
                     json={"session_id": "nope", "message": "hi"})
    assert r.status_code == 200
    assert r.json().get("error") == "unknown session"
