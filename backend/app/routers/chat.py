import json
import uuid
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.schemas.interview import InterviewConfig, InterviewTurn
from app.schemas.profile import UserProfile
from app.services.interview_harness import InterviewSession
from app.services import profile_service as psv

router = APIRouter(prefix="/api/chat", tags=["chat"])
SESSIONS: dict[str, InterviewSession] = {}


@router.post("/session")
async def create_session(config: InterviewConfig):
    """仅创建会话并返回 session_id；首条问题通过 /message (kickoff) 流式推送。"""
    profile = await psv.get_profile()
    sess = InterviewSession(config, profile)
    sid = str(uuid.uuid4())
    SESSIONS[sid] = sess
    return {"session_id": sid}


def _error_stream(message: str):
    payload = json.dumps({"type": "error", "message": message}, ensure_ascii=False)
    yield f"event: error\ndata: {payload}\n\n"


@router.post("/message")
async def send_message(payload: dict):
    """SSE 流式对话端点。

    请求体：{ session_id, message, kickoff? }
      - kickoff=true 且不带 message 时生成首条问题；
      - 否则针对 message 评测并生成下一道问题（或总结）。

    响应（text/event-stream）：
      data: {"type":"token","text":...}   逐段问题正文
      data: {"type":"turn","turn":{...}}   完整 InterviewTurn（评分/引用）
      data: {"type":"done"}                正常结束
      event: error\\ndata: {"type":"error","message":...}  异常中断
    """
    sid = payload.get("session_id")
    sess = SESSIONS.get(sid)
    if not sess:
        return StreamingResponse(_error_stream("unknown session"), media_type="text/event-stream")

    kickoff = bool(payload.get("kickoff", False))
    message = payload.get("message", "") or ""

    async def event_stream():
        try:
            async for ev in sess.stream_answer(message, kickoff=kickoff):
                if ev["type"] == "token":
                    yield f"data: {json.dumps({'type': 'token', 'text': ev['text']}, ensure_ascii=False)}\n\n"
                elif ev["type"] == "turn":
                    yield f"data: {json.dumps({'type': 'turn', 'turn': ev['turn']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:  # 流式过程中的异常：回传 error 事件后关闭
            logging.exception("chat stream failed")
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
