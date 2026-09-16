from app.db.database import SessionLocal
from app.db.models import InterviewRecord
from app.schemas.knowledge import InterviewRecordCreate, InterviewRecordRead
from app.rag import embedder, store
import sqlalchemy


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
    return True


async def import_records(items: list[InterviewRecordCreate]) -> int:
    n = 0
    for it in items:
        await create_record(it); n += 1
    return n
