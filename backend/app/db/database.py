import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Base

def _engine():
    path = os.getenv("DB_PATH", "sqlite+aiosqlite:///./speak_agent.db")
    return create_async_engine(path, echo=False)

engine = _engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
