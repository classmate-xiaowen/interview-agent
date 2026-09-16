from pydantic import BaseModel
from typing import Optional, Literal
from enum import Enum


class State(str, Enum):
    ASKING = "asking"
    EVALUATING = "evaluating"
    SUMMARY = "summary"


class RecordRef(BaseModel):
    record_id: str
    snippet: str


class Evaluation(BaseModel):
    score: int  # 0-100
    covered_points: list[str] = []
    missing_points: list[str] = []
    structure_feedback: str = ""
    expression_feedback: str = ""
    suggestions: list[str] = []


class InterviewTurn(BaseModel):
    question: str
    question_type: Literal["behavioral", "technical", "pressure", "follow_up"]
    references: list[RecordRef] = []
    evaluation: Optional[Evaluation] = None
    ask_followup: bool = False
    followup_question: Optional[str] = None


class InterviewConfig(BaseModel):
    target_company: Optional[str] = None
    target_role: Optional[str] = None
    interviewer_style: Literal["pressure", "gentle", "deep"] = "gentle"
