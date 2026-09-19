from typing import Literal
from pydantic import BaseModel

PII_CATEGORIES = ["name", "phone", "email", "id_card", "company", "address", "social"]


class PiiItem(BaseModel):
    category: str          # 见 PII_CATEGORIES
    text: str
    start: int
    end: int


class MaskSelection(BaseModel):
    start: int
    end: int
    category: str
    action: Literal["mask", "placeholder", "ignore"]


class DetectRequest(BaseModel):
    text: str


class DetectResponse(BaseModel):
    items: list[PiiItem]


class MaskRequest(BaseModel):
    text: str
    selections: list[MaskSelection]


class MaskResponse(BaseModel):
    masked_text: str
    applied: list[PiiItem]   # 实际被打码/占位符的项（不含 ignore）
