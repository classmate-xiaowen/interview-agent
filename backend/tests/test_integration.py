import app.services.interview_harness as h
import app.services.llm as llm
from app.schemas.interview import InterviewTurn, Evaluation, State


def test_end_to_end(test_app, monkeypatch):
    counter = {"n": 0}

    async def fake_llm(system, user, response_model, model=None):
        counter["n"] += 1
        if "面试结束" in user:
            return InterviewTurn(question="总结与改进建议", question_type="behavioral",
                                evaluation=Evaluation(score=70))
        if "EVAL" in user:
            return InterviewTurn(question=f"下一题{counter['n']}", question_type="technical",
                                evaluation=Evaluation(score=70))
        return InterviewTurn(question=f"问题{counter['n']}", question_type="behavioral")

    monkeypatch.setattr(llm, "chat_structured", fake_llm)
    async def fake_query(*a, **k):
        return []
    monkeypatch.setattr(h.store, "query_chunks", fake_query)

    s = test_app.post("/api/chat/session", json={})
    assert s.status_code == 200
    sid = s.json()["session_id"]
    for _ in range(5):
        with test_app.stream("POST", "/api/chat/message",
                             json={"session_id": sid, "message": "回答"}) as r:
            body = "".join(line for line in r.iter_lines())
        assert "event: turn" in body
    # 第 6 次应进入 SUMMARY（max_questions=5）
    with test_app.stream("POST", "/api/chat/message",
                         json={"session_id": sid, "message": "最后回答"}) as r:
        body = "".join(line for line in r.iter_lines())
    assert "总结" in body or "改进" in body
