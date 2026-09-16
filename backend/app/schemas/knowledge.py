from pydantic import BaseModel
from typing import Optional, Literal


class InterviewRecordCreate(BaseModel):
    question: str
    my_answer: Optional[str] = None
    reference_answer: Optional[str] = None
    company: Optional[str] = None
    department: Optional[str] = None
    interviewer_mindset: list[str] = []
    difficulty: Optional[int] = None
    result: Optional[Literal["passed", "failed", "pending"]] = None
    note: Optional[str] = None


class InterviewRecordRead(InterviewRecordCreate):
    id: str
    created_at: str
