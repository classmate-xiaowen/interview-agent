from fastapi import APIRouter
from app.schemas.knowledge import (
    InterviewRecordCreate, InterviewRecordRead, ParseRequest, ParsedQuestionBank,
)
from app.services import knowledge_service as ks

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/parse", response_model=ParsedQuestionBank)
async def parse(req: ParseRequest):
    """AI 解析：把任意原始文本拆成结构化面试题（仅内容字段）。"""
    return await ks.parse_bank(req.text)


@router.post("/records", response_model=InterviewRecordRead)
async def create(data: InterviewRecordCreate):
    return await ks.create_record(data)


@router.get("/records", response_model=list[InterviewRecordRead])
async def list_records(company: str | None = None, mindset: str | None = None, page: int = 1, size: int = 20):
    return await ks.list_records(company, mindset, page, size)


@router.delete("/records/{id}")
async def delete(id: str):
    ok = await ks.delete_record(id)
    return {"deleted": ok}


@router.post("/import")
async def import_records(items: list[InterviewRecordCreate]):
    n = await ks.import_records(items)
    return {"imported": n}
