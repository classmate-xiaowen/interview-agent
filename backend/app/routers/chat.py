import json
import uuid
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.schemas.interview import InterviewConfig, InterviewTurn
from app.schemas.profile import UserProfile
from app.services.interview_harness import InterviewSession
from app.services import profile_service as psv
from app.services import chat_service as cs

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 内存会话缓存：运行期复用 InterviewSession 状态机；不存在时从数据库按需重建。
SESSIONS: dict[str, InterviewSession] = {}


async def _get_or_load_session(sid: str | None) -> InterviewSession | None:
    """按 sid 取内存会话；不存在则从数据库重建（恢复 config/history），支撑续聊与重启恢复。"""
    if not sid:
        return None
    sess = SESSIONS.get(sid)
    if sess:
        return sess
    row = await cs.get_session(sid)
    if not row:
        return None
    profile = await psv.get_profile()
    config = InterviewConfig(
        target_company=row.target_company,
        target_role=row.target_role,
        target_jd=row.target_jd,
        salary=row.salary,
        rounds=row.rounds,
        interviewer_style=row.interviewer_style,
    )
    sess = InterviewSession(config, profile)
    msgs = await cs.get_messages(sid)
    sess.history = [{"role": m.role, "content": m.content} for m in msgs]
    sess.questions_asked = sum(1 for m in msgs if m.role == "user")
    SESSIONS[sid] = sess
    return sess


@router.post("/session")
async def create_session(config: InterviewConfig):
    """仅创建会话并返回 session_id；首条问题通过 /message (kickoff) 流式推送。"""
    profile = await psv.get_profile()
    sess = InterviewSession(config, profile)
    row = await cs.create_session_row(config)
    SESSIONS[row.id] = sess
    return {"session_id": row.id}


@router.get("/sessions")
async def list_sessions():
    """会话列表（按最近更新倒序），供前端历史会话侧栏展示。"""
    rows = await cs.list_sessions()
    return [
        {
            "session_id": r.id,
            "title": r.title,
            "interviewer_style": r.interviewer_style,
            "target_company": r.target_company,
            "target_role": r.target_role,
            "target_jd": r.target_jd,
            "salary": r.salary,
            "rounds": r.rounds,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.get("/sessions/{sid}/messages")
async def get_session_messages(sid: str):
    """会话历史消息（按时间正序），供前端点击历史会话后回看与续聊。"""
    rows = await cs.get_messages(sid)
    return [
        {
            "role": m.role,
            "content": m.content,
            "turn": json.loads(m.turn_json) if m.turn_json else None,
            "created_at": m.created_at,
        }
        for m in rows
    ]


def _error_stream(message: str):
    payload = json.dumps({"type": "error", "message": message}, ensure_ascii=False)
    yield f"event: error\ndata: {payload}\n\n"


@router.post("/message")
async def send_message(payload: dict):
    """SSE 流式对话端点。

    请求体：{ session_id, message, kickoff? }
      - kickoff=true 且不带 message 时生成首条问题；
      - 否则针对 message 评测并生成下一道问题（或总结）。

    每轮消息在成功生成后落库（user + assistant），保证历史可回看、可续聊。
    """
    sess = await _get_or_load_session(payload.get("session_id"))
    if not sess:
        return StreamingResponse(_error_stream("unknown session"), media_type="text/event-stream")

    kickoff = bool(payload.get("kickoff", False))
    message = payload.get("message", "") or ""
    sid = payload.get("session_id")

    async def event_stream():
        try:
            async for ev in sess.stream_answer(message, kickoff=kickoff):
                if ev["type"] == "token":
                    yield f"data: {json.dumps({'type': 'token', 'text': ev['text']}, ensure_ascii=False)}\n\n"
                elif ev["type"] == "turn":
                    turn = ev["turn"]
                    # 一轮成功完成：落库 user（非 kickoff）与 assistant。
                    if not kickoff and message:
                        await cs.append_message(sid, "user", message)
                        await cs.update_session_title(sid, message)
                    await cs.append_message(
                        sid,
                        "assistant",
                        turn.get("question", ""),
                        json.dumps(turn, ensure_ascii=False),
                    )
                    await cs.touch_session(sid)
                    yield f"data: {json.dumps({'type': 'turn', 'turn': turn}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:  # 流式过程中的异常：回传 error 事件后关闭
            logging.exception("chat stream failed")
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/sessions/{sid}")
async def rename_session(sid: str, payload: dict):
    """重命名会话标题。"""
    title = (payload.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "empty title"}
    await cs.rename_session(sid, title)
    return {"ok": True}


@router.delete("/sessions/{sid}")
async def delete_session(sid: str):
    """删除会话及其全部消息。"""
    removed = await cs.delete_session(sid)
    SESSIONS.pop(sid, None)
    return {"deleted": removed}
