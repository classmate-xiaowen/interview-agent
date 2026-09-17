from app.db.database import SessionLocal
from app.db.models import InterviewRecord
from app.schemas.knowledge import (
    InterviewRecordCreate, InterviewRecordRead, ParsedQuestionBank,
)
from app.rag import embedder, store
from app.services import llm
import sqlalchemy

# AI 题库解析系统提示：只抽取内容字段，不猜测元数据（公司/部门/难度等留给用户）。
_PARSE_SYSTEM = """你是一个面试题库整理助手。用户会粘贴任意杂乱的面试笔记、对话记录、文档或零散想法（可能是纯文本或 Markdown）。

请按以下规则整理：
1. 把内容拆分成若干道**独立、语义完整**的面试题，每题一个明确的 question。
2. 若原文包含用户对某题的回答，整理进 my_answer；若包含参考答案或要点，整理进 reference_answer。
3. 自动纠正语病，并可基于常识合理补充缺失的参考答案要点（不得臆造事实）。
4. 把口语化、零散的内容结构化为清晰的题目与答案。
5. 去除重复、合并高度相似的问题，保证每题不重复。
6. 只抽取内容字段（question / my_answer / reference_answer / note），不要猜测公司、部门、难度、结果等元数据。

严格按给定 JSON Schema 返回。questions 数量为 0~30 条；若内容完全无法拆出任何面试题目，返回空数组。"""


def _to_read(r: InterviewRecord) -> InterviewRecordRead:
    return InterviewRecordRead(
        id=r.id, question=r.question, my_answer=r.my_answer,
        reference_answer=r.reference_answer, company=r.company,
        department=r.department, interviewer_mindset=r.interviewer_mindset or [],
        difficulty=r.difficulty, result=r.result, note=r.note, created_at=r.created_at,
    )


async def _index(record_id: str, text: str, meta: dict):
    from app.rag.chunker import chunk_text
    chunks = chunk_text(text)
    if not chunks:
        return
    vecs = await embedder.embed(chunks)
    docs = [{"id": f"{record_id}#{i}", "text": c,
             "metadata": {**meta, "record_id": record_id}}
            for i, c in enumerate(chunks)]
    await store.add_chunks(docs)


async def create_record(data: InterviewRecordCreate) -> InterviewRecordRead:
    async with SessionLocal() as s:
        r = InterviewRecord(**data.model_dump())
        s.add(r); await s.commit(); await s.refresh(r)
        read = _to_read(r)
    await _index(r.id, f"{data.question}\n{data.my_answer or ''}\n{data.reference_answer or ''}",
                 {"company": data.company or "", "department": data.department or "",
                  "mindset": ",".join(data.interviewer_mindset)})
    return read


async def list_records(company=None, mindset=None, page=1, size=20) -> list[InterviewRecordRead]:
    async with SessionLocal() as s:
        q = await s.execute(sqlalchemy.select(InterviewRecord))
        rows = q.scalars().all()
    out = [_to_read(r) for r in rows]
    if company:
        out = [r for r in out if r.company == company]
    if mindset:
        out = [r for r in out if mindset in r.interviewer_mindset]
    return out[(page - 1) * size: page * size]


async def delete_record(id: str) -> bool:
    async with SessionLocal() as s:
        r = await s.get(InterviewRecord, id)
        if not r:
            return False
        await s.delete(r); await s.commit()
    # 同步清理向量库中的相关分块，避免孤儿向量影响后续语义召回
    try:
        await store.delete_chunks_by_record(id)
    except Exception as e:
        print(f"[warn] 清理向量失败 record_id={id}: {e}")
    return True


async def import_records(items: list[InterviewRecordCreate]) -> int:
    n = 0
    for it in items:
        await create_record(it); n += 1
    return n


async def parse_bank(raw_text: str) -> ParsedQuestionBank:
    """调用 LLM 把任意原始文本拆成结构化面试题（仅内容字段）。"""
    text = (raw_text or "").strip()
    if not text:
        return ParsedQuestionBank(questions=[])
    bank = await llm.chat_structured(_PARSE_SYSTEM, text, ParsedQuestionBank)
    # 清洗：丢弃空题、限流到 30 条，避免异常输出污染。
    cleaned = [q for q in bank.questions if q.question and q.question.strip()]
    return ParsedQuestionBank(questions=cleaned[:30])
