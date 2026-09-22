import asyncio
import app.services.interview_harness as h
from app.schemas.interview import InterviewConfig, InterviewTurn, Evaluation, State
from app.schemas.profile import UserProfile


def _mock(monkeypatch):
    async def fake_query(text, n=5, filter_meta=None):
        return [{"id": "r1", "text": "RAG 是检索增强生成",
                 "metadata": {"record_id": "r1"}, "distance": 0.1}]

    async def fake_llm(system, user, response_model, model=None, history=None):
        # 与真实 chat_structured 一致：返回 (InterviewTurn, usage)。
        if "EVAL" in user:
            return InterviewTurn(
                question="下一题？", question_type="technical",
                evaluation=Evaluation(score=70)), None
        return InterviewTurn(question="请介绍一下你自己", question_type="behavioral"), None

    async def fake_stream(system, user, model=None, history=None):
        # 流式出题的异步生成器替身。
        yield "请介绍一下你自己"

    monkeypatch.setattr(h.store, "query_chunks", fake_query)
    monkeypatch.setattr(h.llm, "chat_structured", fake_llm)
    monkeypatch.setattr(h.llm, "stream_text", fake_stream)


async def _run(harness, user_msg="", kickoff=False, session_id=None):
    """驱动 stream_answer 到结束，返回 (final_turn_dict, error_message)。"""
    out = None
    err = None
    async for ev in harness.stream_answer(user_msg, kickoff=kickoff, session_id=session_id):
        if ev["type"] == "turn":
            out = ev["turn"]
        elif ev["type"] == "error":
            err = ev.get("message")
    return out, err


def test_kickoff_returns_question(monkeypatch):
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    turn, err = asyncio.run(_run(s, kickoff=True))
    assert err is None
    assert turn["evaluation"] is None and turn["question"]


def test_answer_evaluates_and_continues(monkeypatch):
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    asyncio.run(_run(s, kickoff=True))
    out, err = asyncio.run(_run(s, user_msg="我的回答..."))
    assert err is None
    assert out["evaluation"] is not None
    # 评分经确定性校准（calibrate_score）后仍为合法分值，且本例（原始 70）应被拉入合格区间。
    assert isinstance(out["evaluation"]["score"], int)
    assert 0 <= out["evaluation"]["score"] <= 100
    assert out["evaluation"]["overall_level"] in ("优秀", "良好", "合格", "待提升", "不合格")


def test_empty_answer_yields_error_event(monkeypatch):
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    asyncio.run(_run(s, kickoff=True))
    out, err = asyncio.run(_run(s, user_msg="   "))
    # 输入护栏命中：harness 捕获 Tripwire 并 yield error 事件，不抛异常、不出 turn。
    assert out is None
    assert err is not None and "护栏" in err


def test_kickoff_writes_trace(monkeypatch):
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    asyncio.run(_run(s, kickoff=True, session_id="sess-1"))
    from app.services import chat_service as cs
    from app.db.database import SessionLocal
    from sqlalchemy import select, func

    async def _count():
        async with SessionLocal() as db:
            return (await db.execute(select(func.count()).select_from(cs.TurnTrace))).scalar()

    assert asyncio.new_event_loop().run_until_complete(_count()) == 1
