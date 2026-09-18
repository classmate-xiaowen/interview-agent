import datetime
import uuid
from sqlalchemy import String, Integer, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InterviewRecord(Base):
    __tablename__ = "interview_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    question: Mapped[str] = mapped_column(Text)
    my_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    interviewer_mindset: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.datetime.now().isoformat())


class UserProfileRow(Base):
    __tablename__ = "user_profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    skills: Mapped[str] = mapped_column(Text, default="")
    years: Mapped[int] = mapped_column(Integer, default=0)
    target_role: Mapped[str] = mapped_column(Text, default="")
    target_companies: Mapped[list] = mapped_column(JSON, default=list)
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    market_context: Mapped[str] = mapped_column(Text, default="")


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String, default="新会话")
    interviewer_style: Mapped[str] = mapped_column(String, default="gentle")
    target_company: Mapped[str | None] = mapped_column(String, nullable=True)
    target_role: Mapped[str | None] = mapped_column(String, nullable=True)
    target_jd: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary: Mapped[str | None] = mapped_column(String, nullable=True)
    rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.datetime.now().isoformat())
    updated_at: Mapped[str] = mapped_column(String, default=lambda: datetime.datetime.now().isoformat())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text)
    turn_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # InterviewTurn JSON (assistant only)
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.datetime.now().isoformat())
