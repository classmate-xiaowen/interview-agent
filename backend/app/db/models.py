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
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)


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
    max_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


class TurnTrace(Base):
    """每轮面试 turn 的可观测 trace（旁路落库，不影响主对话）。

    用于：点评质量回放/eval、评分漂移审计、token 成本统计（NFR-4/NFR-8）。
    prompt_version 支持 prompt/评分框架的灰度与回滚对照。
    """
    __tablename__ = "turn_traces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String, default="answer")  # kickoff | answer | summary
    model: Mapped[str] = mapped_column(String, default="")
    prompt_version: Mapped[str] = mapped_column(String, default="")
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)  # 截断 512 字
    user_input: Mapped[str | None] = mapped_column(Text, nullable=True)      # 截断 512 字（不可信输入）
    retrieved_refs: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: 检索到的知识块
    raw_llm_output: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: 校准前模型原始输出
    interview_turn: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: 最终结构化回合
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str | None] = mapped_column(String, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 评该轮时的难度档（重算校准分所需）
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="ok")  # ok | rejected | error
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.datetime.now().isoformat())
