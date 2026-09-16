import asyncio
import app.services.interview_harness as h
from app.schemas.interview import InterviewConfig, InterviewTurn, Evaluation, State
from app.schemas.profile import UserProfile


def _mock(monkeypatch):
    async def fake_query(text, n=5, filter_meta=None):
        return [{"id": "r1", "text": "RAG 是检索增强生成",
                 "metadata": {"record_id": "r1"}, "distance": 0.1}]
    async def fake_llm(system, user, response_model, model=None):
        if "EVAL" in user:
            return InterviewTurn(
                question="下一题？", question_type="technical",
                evaluation=Evaluation(score=70))
        return InterviewTurn(question="请介绍一下你自己", question_type="behavioral")
    monkeypatch.setattr(h.store, "query_chunks", fake_query)
    monkeypatch.setattr(h.llm, "chat_structured", fake_llm)


def test_start_returns_question(monkeypatch):
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    turn = asyncio.run(s.start())
    assert turn.evaluation is None and turn.question


def test_answer_evaluates_and_continues(monkeypatch):
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    turn = asyncio.run(s.start())
    assert turn.evaluation is None
    out = asyncio.run(s.answer("我的回答..."))
    assert out.evaluation is not None
    assert out.evaluation.score == 70


def test_empty_answer_triggers_tripwire(monkeypatch):
    import pytest
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    asyncio.run(s.start())
    with pytest.raises(h.guardrails.Tripwire):
        asyncio.run(s.answer("   "))
