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
