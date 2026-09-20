from pydantic import BaseModel
from typing import Optional, Literal
from enum import Enum


class State(str, Enum):
    ASKING = "asking"
    EVALUATING = "evaluating"
    SUMMARY = "summary"


# 与 InterviewTurn.question_type 的 Literal 取值保持一致，供 harness 标注类型用。
QuestionType = Literal["behavioral", "technical", "pressure", "follow_up"]


class RecordRef(BaseModel):
    record_id: str
    snippet: str


class CorrectedAnswer(BaseModel):
    """相对用户原回答的纠正版本，与评分/建议逻辑解耦，便于对照。"""
    corrected_text: str = ""          # 改写后的完整回答（可直接照读）
    change_points: list[str] = []     # 相对原回答的明确修改点（聚焦具体改动，不重复 suggestions）


class Evaluation(BaseModel):
    score: int  # 0-100
    overall_level: Literal["优秀", "良好", "合格", "待提升", "不合格"] | None = None  # 国内 5 级定性结论（确定性推导，与数字分解耦）
    covered_points: list[str] = []
    missing_points: list[str] = []
    structure_feedback: str = ""
    expression_feedback: str = ""
    suggestions: list[str] = []
    corrected_answer: CorrectedAnswer | None = None


class InterviewTurn(BaseModel):
    question: str
    question_type: Literal["behavioral", "technical", "pressure", "follow_up"]
    references: list[RecordRef] = []
    evaluation: Optional[Evaluation] = None
    ask_followup: bool = False
    followup_question: Optional[str] = None
    is_summary: bool = False  # 标记本回合为面试总结/整体点评（非面试题，不应导入知识库）


class InterviewConfig(BaseModel):
    target_company: Optional[str] = None
    target_role: Optional[str] = None
    target_jd: Optional[str] = None      # 岗位 JD / 招聘要求（提示词初始化上下文）
    salary: Optional[str] = None         # 薪资范围（提示词初始化上下文）
    rounds: Optional[int] = None         # 第几轮面试（提示词上下文，非硬性停止条件）
    interviewer_style: Literal["pressure", "gentle", "deep"] = "gentle"
    max_questions: Optional[int] = None  # 单场题目数量上限（覆盖 config.max_questions 全局默认值）
