import os

os.environ["DB_PATH"] = "sqlite+aiosqlite:///./.test_speak_agent.db"
os.environ["CHROMA_DIR"] = "./.test_chroma"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["LLM_BASE_URL"] = "https://api.openai.com/v1"
os.environ["MAX_QUESTIONS"] = "5"

import asyncio
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_app():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    from app.db.database import engine
    from app.db.models import Base
    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    asyncio.new_event_loop().run_until_complete(_reset())
    yield
