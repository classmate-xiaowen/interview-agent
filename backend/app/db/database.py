import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Base

def _engine():
    path = os.getenv("DB_PATH", "sqlite+aiosqlite:///./speak_agent.db")
    return create_async_engine(path, echo=False)

engine = _engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# create_all 只会建缺失的表，不会给已有表加列。这里为旧库补齐新增列，避免 INSERT 报错。
_MISSING_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "chat_sessions": [
        ("target_jd", "TEXT"),
        ("salary", "TEXT"),
        ("rounds", "INTEGER"),
        ("max_questions", "INTEGER"),
    ],
    "user_profile": [
        ("resume_text", "TEXT"),
    ],
}

async def _migrate_columns():
    async with engine.begin() as conn:
        for table, cols in _MISSING_COLUMNS.items():
            def _info(sync_conn, t=table):
                return sync_conn.execute(text(f"PRAGMA table_info({t})")).fetchall()
            rows = await conn.run_sync(_info)
            existing = {r[1] for r in rows}
            for col, ctype in cols:
                if col not in existing:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}"))

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_columns()
