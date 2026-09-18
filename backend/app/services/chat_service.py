"""会话与消息的持久化层（ChatSession / ChatMessage）。

职责：
- 新建会话行、追加消息、列出会话、读取历史、更新标题与时间戳。
- 仅做 CRUD，不关心 InterviewSession 的内存状态机。
"""
from app.db.database import SessionLocal
from app.db.models import ChatSession, ChatMessage
from app.schemas.interview import InterviewConfig

_STYLE_LABEL = {"pressure": "高压型", "gentle": "温和型", "deep": "深挖型"}


async def create_session_row(config: InterviewConfig) -> ChatSession:
    style = config.interviewer_style or "gentle"
    title = f"{_STYLE_LABEL.get(style, '温和型')}模拟面试"
    row = ChatSession(
        title=title,
        interviewer_style=style,
        target_company=config.target_company,
        target_role=config.target_role,
    )
    async with SessionLocal() as s:
        s.add(row)
        await s.commit()
        await s.refresh(row)
    return row


async def append_message(
    session_id: str, role: str, content: str, turn_json: str | None = None
) -> None:
    msg = ChatMessage(session_id=session_id, role=role, content=content, turn_json=turn_json)
    async with SessionLocal() as s:
        s.add(msg)
        sess = await s.get(ChatSession, session_id)
        if sess:
            import datetime

            sess.updated_at = datetime.datetime.now().isoformat()
        await s.commit()


async def list_sessions() -> list[ChatSession]:
    async with SessionLocal() as s:
        from sqlalchemy import select

        rows = (
            await s.execute(select(ChatSession).order_by(ChatSession.updated_at.desc()))
        ).scalars().all()
    return list(rows)


async def get_session(session_id: str) -> ChatSession | None:
    async with SessionLocal() as s:
        return await s.get(ChatSession, session_id)


async def get_messages(session_id: str) -> list[ChatMessage]:
    async with SessionLocal() as s:
        from sqlalchemy import select

        rows = (
            await s.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.asc())
            )
        ).scalars().all()
    return list(rows)


async def update_session_title(session_id: str, title: str) -> None:
    async with SessionLocal() as s:
        sess = await s.get(ChatSession, session_id)
        if sess and (sess.title == "新会话" or sess.title.endswith("模拟面试")):
            sess.title = title[:30]
        await s.commit()


async def touch_session(session_id: str) -> None:
    async with SessionLocal() as s:
        sess = await s.get(ChatSession, session_id)
        if sess:
            import datetime

            sess.updated_at = datetime.datetime.now().isoformat()
        await s.commit()


async def rename_session(session_id: str, title: str) -> None:
    title = title.strip()[:30]
    if not title:
        return
    async with SessionLocal() as s:
        sess = await s.get(ChatSession, session_id)
        if sess:
            sess.title = title
            await s.commit()


async def delete_session(session_id: str) -> bool:
    async with SessionLocal() as s:
        from sqlalchemy import delete

        await s.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
        sess = await s.get(ChatSession, session_id)
        if not sess:
            return False
        await s.delete(sess)
        await s.commit()
    return True
