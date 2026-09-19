from fastapi import APIRouter
from app.schemas.resume import DetectRequest, DetectResponse, MaskRequest, MaskResponse
from app.services import pii

router = APIRouter(prefix="/api/resume", tags=["resume"])


@router.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    """无状态：仅做 PII 检测，不持久化原文。"""
    return DetectResponse(items=pii.detect_pii(req.text))


@router.post("/mask", response_model=MaskResponse)
async def mask(req: MaskRequest):
    """无状态：按用户选择生成脱敏文本，不持久化原文。"""
    masked_text, applied = pii.apply_masks(req.text, req.selections)
    return MaskResponse(masked_text=masked_text, applied=applied)
