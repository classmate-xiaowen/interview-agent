import json
import uuid
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
    profile = await psv.get_profile()
    sess = InterviewSession(config, profile)
    turn = await sess.start()
    sid = str(uuid.uuid4())
    SESSIONS[sid] = sess
    return {"session_id": sid, **turn.model_dump()}


def _split(text: str, size: int = 8):
    for i in range(0, len(text), size):
        yield text[i:i + size]


@router.post("/message")
async def send_message(payload: dict):
    sid = payload.get("session_id")
    sess = SESSIONS.get(sid)
    if not sess:
        return {"error": "unknown session"}
    turn = await sess.answer(payload.get("message", ""))

    async def event_stream():
        for piece in _split(turn.question):
            yield f"data: {json.dumps({'type': 'token', 'text': piece}, ensure_ascii=False)}\n\n"
        yield f"event: turn\ndata: {turn.model_dump_json()}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
