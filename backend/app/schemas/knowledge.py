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


class ParseRequest(BaseModel):
    """AI 题库解析请求：传入任意原始文本。"""
    text: str


class ParsedQuestion(BaseModel):
    """AI 解析出的单道题（仅内容字段，不含元数据）。"""
    question: str
    my_answer: Optional[str] = None
    reference_answer: Optional[str] = None
    note: Optional[str] = None


class ParsedQuestionBank(BaseModel):
    questions: list[ParsedQuestion]
