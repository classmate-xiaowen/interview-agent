# 面试训练 Agent — MVP (知识库 + RAG + 对话 + Harness/护栏) 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一个可本地运行的最小可用面试教练后端——支持面试记录入库 + 向量化检索（RAG）、用户画像、以及由确定性状态机 + 结构化输出 + 护栏驱动的模拟面试 Agent 对话。

**Architecture:** 单体 FastAPI 服务。数据层 = SQLite（结构化元数据）+ Chroma（向量）。Agent 部分用自研轻量 Harness（状态机 `ASKING→EVALUATING→SUMMARY` + ReAct 式检索-生成循环），结构化输出用 `instructor` 在解码层强制 Pydantic Schema，输入/输出经 Guardrail + Tripwire 校验，保证 I/O 一致、防止漂移（设计见需求文档 §3.3–3.4）。选择自研状态机而非引入 LangGraph，遵循 YAGNI、减少依赖、便于单元测试；接口形态与 LangGraph 式 StateGraph 对齐，后续可平滑迁移。

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, SQLAlchemy(async)+aiosqlite, Chroma(persistent), openai(OpenAI 兼容 SDK), instructor(结构化输出), pydantic / pydantic-settings, pytest + pytest-asyncio + httpx(ASGI 测试)。

**Spec:** `docs/interview-agent-requirements.md`（v1.0，含 §3.3–3.6 Harness 与防漂移、NFR-7/8）

## Global Constraints
- NFR-1 隐私：所有数据默认本地存储；模型调用仅传必要上下文，绝不传原始简历。
- NFR-2 可配置：`llm_base_url` / `llm_api_key` / `chat_model` / `embed_model` 经 `.env` 或环境变量注入，禁止硬编码。
- NFR-3 性能：对话首字延迟 < 3s（依赖模型）；RAG 检索 < 500ms。
- NFR-7 一致性：所有 Agent 回复必须遵循 `InterviewTurn` Pydantic Schema；面试流程由确定性状态机驱动；输出须带 `references`；输入/输出经护栏校验。验收：连续 10 轮回合结构 100% 可解析、无格式漂移。
- NFR-8 可观测：每次 turn 记录输入/输出/检索/评分/耗时/token。
- 代码风格：每个文件单一职责；TDD（先写失败测试 → 最小实现 → 通过 → 提交）；频繁小提交。

---

## 文件结构（任务落地锁定）

```
backend/
  requirements.txt
  .env.example
  app/
    __init__.py
    main.py                  # FastAPI app + CORS + 路由挂载 + 启动 init_db
    config.py                # pydantic-settings: 模型/向量/DB 配置
    db/
      __init__.py
      database.py            # async engine + SessionLocal + init_db
      models.py              # ORM: InterviewRecord, UserProfileRow
    schemas/
      __init__.py
      knowledge.py           # InterviewRecordCreate / InterviewRecordRead
      interview.py           # InterviewConfig / InterviewTurn / Evaluation / RecordRef / State
      profile.py             # UserProfile
    rag/
      __init__.py
      embedder.py            # embed(texts) -> list[list[float]]
      chunker.py             # chunk_text(text) -> list[str]
      store.py               # add_chunks / query_chunks (Chroma 包装)
    services/
      __init__.py
      llm.py                 # chat_structured(...) instructor 封装
      guardrails.py          # input_guardrail / output_guardrail + Tripwire
      knowledge_service.py   # create/list/delete/import + 入向量库
      profile_service.py     # get/update 单行人画像
      interview_harness.py   # InterviewSession 状态机 + Agent Loop
    routers/
      __init__.py
      knowledge.py           # CRUD + 批量导入
      profile.py
      chat.py                # SSE 会话与消息
  tests/
    conftest.py
    test_knowledge.py
    test_rag_store.py
    test_guardrails.py
    test_interview_harness.py
```

---

### Task 1: 项目脚手架与配置

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/main.py`
- Create: `backend/app/db/__init__.py`, `backend/app/db/database.py`

**Interfaces:**
- Produces: `settings` (全局配置单例), `init_db()`, FastAPI `app`

- [ ] **Step 1: 写 `backend/requirements.txt`**
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
aiosqlite==0.20.0
chromadb==0.5.5
openai==1.45.0
instructor==1.5.0
pydantic==2.9.0
pydantic-settings==2.5.0
python-dotenv==1.0.1
pytest==8.3.2
pytest-asyncio==0.24.0
httpx==0.27.0
```

- [ ] **Step 2: 写 `backend/.env.example`**
```
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
CHAT_MODEL=gpt-4o-mini
EMBED_MODEL=text-embedding-3-small
CHROMA_DIR=./chroma_data
DB_PATH=sqlite+aiosqlite:///./speak_agent.db
MAX_QUESTIONS=5
GUARDRAIL_MODEL=gpt-4o-mini
```

- [ ] **Step 3: 写 `backend/app/config.py`**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    chat_model: str = "gpt-4o-mini"
    embed_model: str = "text-embedding-3-small"
    chroma_dir: str = "./chroma_data"
    db_path: str = "sqlite+aiosqlite:///./speak_agent.db"
    max_questions: int = 5
    guardrail_model: str = "gpt-4o-mini"

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 4: 写 `backend/app/db/database.py`**
```python
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
```

- [ ] **Step 5: 写 `backend/app/main.py`**
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init_db
from app.routers import knowledge, profile, chat

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Interview Agent MVP", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(knowledge.router)
app.include_router(profile.router)
app.include_router(chat.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: 写失败测试 `backend/tests/conftest.py` 与 `test_scaffold.py` 片段**
```python
# tests/conftest.py
import pytest, os
os.environ["DB_PATH"] = "sqlite+aiosqlite:///:memory:"
os.environ["CHROMA_DIR"] = "./.test_chroma"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["LLM_BASE_URL"] = "https://api.openai.com/v1"

@pytest.fixture
def app():
    from app.main import app
    return app
```
```python
# tests/test_scaffold.py
from fastapi.testclient import TestClient  # 仅冒烟用同步客户端

def test_health():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
```

- [ ] **Step 7: 运行测试确认失败（此时 models 未定义会报错）**
Run: `cd backend && pip install -r requirements.txt && pytest tests/test_scaffold.py -q`
Expected: FAIL（ImportError: cannot import name 'Base' from 'app.db.models'）

- [ ] **Step 8: 补 `app/db/models.py` 使导入成立（完整实现见 Task 2，此处先放最小 Base）**
```python
from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase):
    pass
```

- [ ] **Step 9: 运行测试确认通过**
Run: `pytest tests/test_scaffold.py -q`
Expected: PASS

- [ ] **Step 10: Commit**
```bash
git add backend && git commit -m "chore: scaffold FastAPI app, config, db engine"
```

---

### Task 2: 数据模型（ORM）

**Files:**
- Create/Modify: `backend/app/db/models.py` (补全)
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `InterviewRecord`, `UserProfileRow` ORM 类；供 Task 6/8 service 使用。

- [ ] **Step 1: 写失败测试 `test_models.py`**
```python
import pytest
from app.db.database import SessionLocal, init_db
from app.db.models import InterviewRecord, UserProfileRow

@pytest.mark.asyncio
async def test_create_record():
    await init_db()
    async with SessionLocal() as s:
        r = InterviewRecord(question="解释一下 RAG 是什么？", company="Acme", interviewer_mindset=["deep"])
        s.add(r); await s.commit(); await s.refresh(r)
        assert r.id
        assert r.created_at
```
（需在 `tests/conftest.py` 增加 `pytest_plugins = ("pytest_asyncio",)` 与 `asyncio_mode="auto"`；或在 `pyproject/pytest.ini` 配置。）

- [ ] **Step 2: 运行确认失败**
Run: `pytest tests/test_models.py -q` → FAIL（表不存在 / 字段缺失）

- [ ] **Step 3: 写完整 `app/db/models.py`**
```python
import datetime, uuid
from sqlalchemy import String, Integer, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class InterviewRecord(Base):
    __tablename__ = "interview_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    question: Mapped[str] = mapped_column(Text)
    my_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    interviewer_mindset: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.datetime.now().isoformat())

class UserProfileRow(Base):
    __tablename__ = "user_profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    skills: Mapped[str] = mapped_column(Text, default="")
    years: Mapped[int] = mapped_column(Integer, default=0)
    target_role: Mapped[str] = mapped_column(Text, default="")
    target_companies: Mapped[list] = mapped_column(JSON, default=list)
    weaknesses: Mapped[str] = mapped_column(Text, default="")
    market_context: Mapped[str] = mapped_column(Text, default="")
```

- [ ] **Step 4: 运行确认通过**
Run: `pytest tests/test_models.py -q` → PASS

- [ ] **Step 5: Commit**
```bash
git add backend/app/db/models.py backend/tests/test_models.py && git commit -m "feat: add ORM models InterviewRecord & UserProfile"
```

---

### Task 3: Schemas（Pydantic 契约）

**Files:**
- Create: `backend/app/schemas/__init__.py`, `knowledge.py`, `interview.py`, `profile.py`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Produces: `InterviewRecordCreate`, `InterviewRecordRead`, `InterviewConfig`, `InterviewTurn`, `Evaluation`, `RecordRef`, `State`(Enum), `UserProfile` —— 全局复用。

- [ ] **Step 1: 写测试 `test_schemas.py`**
```python
from app.schemas.interview import InterviewTurn, Evaluation, RecordRef

def test_turn_requires_question():
    t = InterviewTurn(question="你如何处理冲突？", question_type="behavioral")
    assert t.ask_followup is False
    assert t.references == []

def test_evaluation_score_bounds_via_model():
    e = Evaluation(score=88, covered_points=["a"], missing_points=["b"])
    assert 0 <= e.score <= 100
```

- [ ] **Step 2: 运行确认失败**（模块不存在）→ FAIL

- [ ] **Step 3: 写 `schemas/knowledge.py`**
```python
from pydantic import BaseModel
from typing import Optional, Literal

class InterviewRecordCreate(BaseModel):
    question: str
    my_answer: Optional[str] = None
    reference_answer: Optional[str] = None
    company: Optional[str] = None
    department: Optional[str] = None
    interviewer_mindset: list[str] = []
    difficulty: Optional[int] = None
    result: Optional[Literal["passed", "failed", "pending"]] = None
    note: Optional[str] = None

class InterviewRecordRead(InterviewRecordCreate):
    id: str
    created_at: str
```

- [ ] **Step 4: 写 `schemas/interview.py`**
```python
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
```

- [ ] **Step 5: 写 `schemas/profile.py`**
```python
from pydantic import BaseModel

class UserProfile(BaseModel):
    skills: str = ""
    years: int = 0
    target_role: str = ""
    target_companies: list[str] = []
    weaknesses: str = ""
    market_context: str = ""
```

- [ ] **Step 6: 运行确认通过** → PASS

- [ ] **Step 7: Commit**
```bash
git add backend/app/schemas && git commit -m "feat: add Pydantic schemas incl. InterviewTurn contract"
```

---

### Task 4: RAG — Embedder

**Files:**
- Create: `backend/app/rag/__init__.py`, `embedder.py`
- Test: `backend/tests/test_embedder.py`

**Interfaces:**
- Produces: `async def embed(texts: list[str]) -> list[list[float]]`（供 Task 6 入库、Task 11 检索使用）

- [ ] **Step 1: 写测试（用 monkeypatch 替换网络调用，保证离线可测）**
```python
import app.rag.embedder as emb

def test_embed_returns_vectors(monkeypatch):
    async def fake_create(*args, **kwargs):
        class D: 
            def __init__(s, v): s.embedding = v
        class R:
            data = [D([0.1, 0.2]), D([0.3, 0.4])]
        return R()
    monkeypatch.setattr(emb._client.embeddings, "create", fake_create)
    import asyncio
    out = asyncio.run(emb.embed(["a", "b"]))
    assert len(out) == 2 and len(out[0]) == 2
```

- [ ] **Step 2: 运行确认失败** → FAIL（模块缺失）

- [ ] **Step 3: 写 `rag/embedder.py`**
```python
from openai import AsyncOpenAI
from app.config import settings

_client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = await _client.embeddings.create(model=settings.embed_model, input=texts)
    return [d.embedding for d in resp.data]
```

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit**
```bash
git add backend/app/rag && git commit -m "feat: OpenAI-compatible embedder"
```

---

### Task 5: RAG — Chunker & Chroma Store

**Files:**
- Create: `backend/app/rag/chunker.py`, `store.py`
- Test: `backend/tests/test_rag_store.py`

**Interfaces:**
- Produces: `chunk_text(text, max_chars=800, overlap=80) -> list[str]`
- Produces: `async def add_chunks(chunks: list[dict])`, `async def query_chunks(text, n=5, filter_meta=None) -> list[dict]`
  - `chunks` 元素: `{"id": str, "text": str, "metadata": dict}`
  - 返回元素: `{"id": str, "text": str, "metadata": dict, "distance": float}`

- [ ] **Step 1: 写测试**
```python
import app.rag.chunker as ch
import app.rag.store as st

def test_chunk_text_splits_long():
    text = "段落一。" * 300 + "\n\n段落二。" * 300
    parts = ch.chunk_text(text, max_chars=400, overlap=40)
    assert len(parts) >= 2
    assert all(len(p) <= 480 for p in parts)

@pytest.mark.asyncio
async def test_add_and_query():
    chunks = [{"id": "c1", "text": "RAG 结合检索与生成", "metadata": {"company": "Acme"}}]
    await st.add_chunks(chunks)
    res = await st.query_chunks("RAG 检索", n=3, filter_meta={"company": "Acme"})
    assert any(r["id"] == "c1" for r in res)
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 写 `rag/chunker.py`**
```python
def chunk_text(text: str, max_chars: int = 800, overlap: int = 80) -> list[str]:
    if not text.strip():
        return []
    # 先按空行分段，再按长度裁剪
    blocks = [b for b in text.split("\n\n") if b.strip()]
    if not blocks:
        blocks = [text]
    out: list[str] = []
    for b in blocks:
        if len(b) <= max_chars:
            out.append(b)
            continue
        start = 0
        while start < len(b):
            seg = b[start:start + max_chars]
            out.append(seg)
            start += max_chars - overlap
    return out
```

- [ ] **Step 4: 写 `rag/store.py`**
```python
import asyncio
import chromadb
from app.config import settings

_client = chromadb.PersistentClient(path=settings.chroma_dir)
_collection = _client.get_or_create_collection("interview_chunks", metadata={"hnsw:space": "cosine"})

async def add_chunks(chunks: list[dict]):
    if not chunks:
        return
    await asyncio.to_thread(
        _collection.add,
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c.get("metadata", {}) for c in chunks],
    )

async def query_chunks(text: str, n: int = 5, filter_meta: dict | None = None) -> list[dict]:
    if not text.strip():
        return []
    res = await asyncio.to_thread(
        _collection.query, query_texts=[text], n_results=n, where=filter_meta
    )
    out = []
    for i, doc in enumerate(res["documents"][0]):
        out.append({
            "id": res["ids"][0][i],
            "text": doc,
            "metadata": (res["metadatas"][0][i] if res["metadatas"] else {}),
            "distance": (res["distances"][0][i] if res["distances"] else 0.0),
        })
    return out
```

- [ ] **Step 5: 运行确认通过** → PASS

- [ ] **Step 6: Commit**
```bash
git add backend/app/rag && git commit -m "feat: chunker + Chroma vector store (add/query)"
```

---

### Task 6: 知识库 Service + Router（CRUD 与入库向量化）

**Files:**
- Create: `backend/app/services/__init__.py`, `knowledge_service.py`
- Create: `backend/app/routers/__init__.py`, `knowledge.py`
- Test: `backend/tests/test_knowledge.py`

**Interfaces:**
- Produces:
  - `async def create_record(data: InterviewRecordCreate) -> InterviewRecordRead`（写入 DB + 切片 + embed + 入 Chroma）
  - `async def list_records(company=None, mindset=None, page=1, size=20) -> list[InterviewRecordRead]`
  - `async def delete_record(id: str) -> bool`
  - `async def import_records(items: list[InterviewRecordCreate]) -> int`（返回入库条数）
- 路由：`POST /api/knowledge/records`、`GET /api/knowledge/records`、`DELETE /api/knowledge/records/{id}`、`POST /api/knowledge/import`

- [ ] **Step 1: 写测试（用 TestClient + monkeypatch embed/store 以离线运行）**
```python
import app.rag.embedder as emb
import app.rag.store as st

def _patch(monkeypatch):
    async def fake_embed(texts): return [[0.0]*8 for _ in texts]
    async def fake_add(chunks): pass
    monkeypatch.setattr(emb, "embed", fake_embed)
    monkeypatch.setattr(st, "add_chunks", fake_add)

def test_create_and_list(test_app, monkeypatch):
    _patch(monkeypatch)
    from app.schemas.knowledge import InterviewRecordCreate
    body = InterviewRecordCreate(question="q1", company="Acme", interviewer_mindset=["deep"]).model_dump()
    r = test_app.post("/api/knowledge/records", json=body)
    assert r.status_code == 200
    rid = r.json()["id"]
    lst = test_app.get("/api/knowledge/records", params={"company": "Acme"})
    assert lst.status_code == 200 and len(lst.json()) >= 1
    d = test_app.delete(f"/api/knowledge/records/{rid}")
    assert d.status_code == 200
```
（`test_app` fixture 见 Task 1 conftest，用 `fastapi.testclient.TestClient(app)`；注意 DB 用内存库且每个测试 `init_db` 重建。）

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 写 `services/knowledge_service.py`**
```python
from app.db.database import SessionLocal
from app.db.models import InterviewRecord
from app.schemas.knowledge import InterviewRecordCreate, InterviewRecordRead
from app.rag import embedder, store

def _to_read(r: InterviewRecord) -> InterviewRecordRead:
    return InterviewRecordRead(
        id=r.id, question=r.question, my_answer=r.my_answer,
        reference_answer=r.reference_answer, company=r.company,
        department=r.department, interviewer_mindset=r.interviewer_mindset or [],
        difficulty=r.difficulty, result=r.result, note=r.note, created_at=r.created_at,
    )

async def create_record(data: InterviewRecordCreate) -> InterviewRecordRead:
    async with SessionLocal() as s:
        r = InterviewRecord(**data.model_dump())
        s.add(r); await s.commit(); await s.refresh(r)
        read = _to_read(r)
    await _index(r.id, f"{data.question}\n{data.my_answer or ''}\n{data.reference_answer or ''}",
                 {"company": data.company or "", "department": data.department or "",
                  "mindset": ",".join(data.interviewer_mindset)})
    return read

async def _index(record_id: str, text: str, meta: dict):
    from app.rag.chunker import chunk_text
    chunks = chunk_text(text)
    if not chunks:
        return
    vecs = await embedder.embed(chunks)
    docs = [{"id": f"{record_id}#{i}", "text": c, "metadata": {**meta, "record_id": record_id}}
            for i, c in enumerate(chunks)]
    await store.add_chunks(docs)

async def list_records(company=None, mindset=None, page=1, size=20) -> list[InterviewRecordRead]:
    async with SessionLocal() as s:
        q = await s.execute(__import__("sqlalchemy").select(InterviewRecord))
        rows = q.scalars().all()
    out = [_to_read(r) for r in rows]
    if company:
        out = [r for r in out if r.company == company]
    if mindset:
        out = [r for r in out if mindset in r.interviewer_mindset]
    return out[(page-1)*size: page*size]

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
```

- [ ] **Step 4: 写 `routers/knowledge.py`**
```python
from fastapi import APIRouter
from app.schemas.knowledge import InterviewRecordCreate, InterviewRecordRead
from app.services import knowledge_service as ks

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

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
```

- [ ] **Step 5: 运行确认通过** → PASS

- [ ] **Step 6: Commit**
```bash
git add backend/app/services backend/app/routers && git commit -m "feat: knowledge service + router (CRUD, vector index, import)"
```

---

### Task 7: 用户画像 Service + Router

**Files:**
- Create: `backend/app/services/profile_service.py`, `backend/app/routers/profile.py`
- Test: `backend/tests/test_profile.py`

**Interfaces:**
- Produces: `async def get_profile() -> UserProfile`、`async def update_profile(data: UserProfile) -> UserProfile`
- 路由：`GET /api/profile`、`PUT /api/profile`

- [ ] **Step 1: 写测试**
```python
def test_profile_roundtrip(test_app):
    r = test_app.put("/api/profile", json={"skills": "Python", "target_role": "后端", "years": 3})
    assert r.status_code == 200 and r.json()["target_role"] == "后端"
    g = test_app.get("/api/profile")
    assert g.json()["skills"] == "Python"
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 写 `services/profile_service.py`**
```python
from app.db.database import SessionLocal
from app.db.models import UserProfileRow
from app.schemas.profile import UserProfile

async def get_profile() -> UserProfile:
    async with SessionLocal() as s:
        row = await s.get(UserProfileRow, 1)
        if not row:
            row = UserProfileRow(); s.add(row); await s.commit(); await s.refresh(row)
        return UserProfile(skills=row.skills, years=row.years, target_role=row.target_role,
                           target_companies=row.target_companies or [], weaknesses=row.weaknesses,
                           market_context=row.market_context)

async def update_profile(data: UserProfile) -> UserProfile:
    async with SessionLocal() as s:
        row = await s.get(UserProfileRow, 1)
        if not row:
            row = UserProfileRow()
        row.skills = data.skills; row.years = data.years; row.target_role = data.target_role
        row.target_companies = data.target_companies; row.weaknesses = data.weaknesses
        row.market_context = data.market_context
        s.add(row); await s.commit(); await s.refresh(row)
        return UserProfile(skills=row.skills, years=row.years, target_role=row.target_role,
                           target_companies=row.target_companies or [], weaknesses=row.weaknesses,
                           market_context=row.market_context)
```

- [ ] **Step 4: 写 `routers/profile.py`**
```python
from fastapi import APIRouter
from app.schemas.profile import UserProfile
from app.services import profile_service as ps

router = APIRouter(prefix="/api", tags=["profile"])

@router.get("/profile", response_model=UserProfile)
async def get_profile():
    return await ps.get_profile()

@router.put("/profile", response_model=UserProfile)
async def update_profile(data: UserProfile):
    return await ps.update_profile(data)
```

- [ ] **Step 5: 运行确认通过** → PASS

- [ ] **Step 6: Commit**
```bash
git add backend/app/services/profile_service.py backend/app/routers/profile.py && git commit -m "feat: user profile service + router"
```

---

### Task 8: LLM 结构化输出封装（instructor）

**Files:**
- Create: `backend/app/services/llm.py`
- Test: `backend/tests/test_llm.py`

**Interfaces:**
- Produces: `async def chat_structured(system: str, user: str, response_model: type[T], model: str | None = None) -> T`
  - 用 `instructor.from_openai(AsyncOpenAI(...))` 强制 JSON Schema 输出。

- [ ] **Step 1: 写测试（monkeypatch instructor client 返回固定对象）**
```python
import app.services.llm as llm
from app.schemas.interview import InterviewTurn

def test_chat_structured_returns_model(monkeypatch):
    async def fake(*a, **k):
        return InterviewTurn(question="q?", question_type="technical")
    monkeypatch.setattr(llm, "_client", type("X", (), {"chat": type("C", (), {
        "completions": type("CC", (), {"create": staticmethod(fake)})})})())
    import asyncio
    out = asyncio.run(llm.chat_structured("sys", "usr", InterviewTurn))
    assert isinstance(out, InterviewTurn) and out.question == "q?"
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 写 `services/llm.py`**
```python
import instructor
from openai import AsyncOpenAI
from app.config import settings

_client = instructor.from_openai(
    AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
)

async def chat_structured(system: str, user: str, response_model: type, model: str | None = None):
    return await _client.chat.completions.create(
        model=model or settings.chat_model,
        response_model=response_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
```

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/llm.py && git commit -m "feat: instructor-backed structured LLM call"
```

---

### Task 9: Guardrails + Tripwire（防漂移输入/输出护栏）

**Files:**
- Create: `backend/app/services/guardrails.py`
- Test: `backend/tests/test_guardrails.py`

**Interfaces:**
- Produces: `class Tripwire(Exception)`、`async def input_guardrail(msg: str) -> None`（触发则抛 `Tripwire`）、`async def output_guardrail(turn: InterviewTurn) -> InterviewTurn`（非法则抛 `Tripwire`）
- 供 Task 11 harness 与 Task 12 router 调用。

- [ ] **Step 1: 写测试**
```python
import pytest
from app.services.guardrails import input_guardrail, output_guardrail, Tripwire
from app.schemas.interview import InterviewTurn, Evaluation

@pytest.mark.asyncio
async def test_input_empty_triggers():
    with pytest.raises(Tripwire):
        await input_guardrail("   ")

@pytest.mark.asyncio
async def test_output_invalid_score_triggers():
    bad = InterviewTurn(question="x", question_type="technical",
                        evaluation=Evaluation(score=150))
    with pytest.raises(Tripwire):
        await output_guardrail(bad)

@pytest.mark.asyncio
async def test_output_valid_passes():
    ok = InterviewTurn(question="x", question_type="technical",
                       evaluation=Evaluation(score=80))
    assert (await output_guardrail(ok)) is ok
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 写 `services/guardrails.py`**
```python
from app.schemas.interview import InterviewTurn, Evaluation

class Tripwire(Exception):
    """护栏触发：输入/输出未通过校验，需中断当前 turn。"""

_BLOCKLIST = ["ignore previous instructions", "忽略前面的指令", "system prompt"]

async def input_guardrail(msg: str) -> None:
    if not msg or not msg.strip():
        raise Tripwire("empty input")
    low = msg.lower()
    if any(b in low for b in _BLOCKLIST):
        raise Tripwire("possible prompt injection")

async def output_guardrail(turn: InterviewTurn) -> InterviewTurn:
    if not turn.question or not turn.question.strip():
        raise Tripwire("empty question in output")
    if turn.evaluation is not None:
        if not (0 <= turn.evaluation.score <= 100):
            raise Tripwire("evaluation score out of range")
    # 类型已由 Pydantic 在解码层保证；此处做语义护栏
    return turn
```

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/guardrails.py && git commit -m "feat: input/output guardrails + Tripwire"
```

---

### Task 10: 面试 Harness — 状态机 + Agent Loop

**Files:**
- Create: `backend/app/services/interview_harness.py`
- Test: `backend/tests/test_interview_harness.py`

**Interfaces:**
- Produces: `class InterviewSession`
  - `__init__(self, config: InterviewConfig, profile: UserProfile)`
  - `async def start(self) -> InterviewTurn`（问候 + 首题，evaluation=None）
  - `async def answer(self, user_msg: str) -> InterviewTurn`（先 input_guardrail → 评上轮 → 决定追问/下一题 → 输出护栏 → 返回；达到 max_questions 转 SUMMARY）
- 内部依赖：`rag.store.query_chunks`、`services.llm.chat_structured`、`services.guardrails`。

- [ ] **Step 1: 写测试（monkeypatch LLM/检索，纯逻辑验证状态机与结构化契约）**
```python
import app.services.interview_harness as h
from app.schemas.interview import InterviewConfig, InterviewTurn, State
from app.schemas.profile import UserProfile

def _mock(monkeypatch):
    async def fake_query(text, n=5, filter_meta=None):
        return [{"id": "r1", "text": "RAG 是检索增强生成", "metadata": {"record_id": "r1"}, "distance": 0.1}]
    async def fake_llm(system, user, response_model, model=None):
        # 依据 user 是否含 'EVAL' 决定返回评测还是提问
        if "EVAL" in user:
            return InterviewTurn(question="下一题？", question_type="technical",
                                 evaluation=__import__("app.schemas.interview", fromlist=["Evaluation"]).Evaluation(score=70))
        return InterviewTurn(question="请介绍一下你自己", question_type="behavioral")
    monkeypatch.setattr(h.store, "query_chunks", fake_query)
    monkeypatch.setattr(h.llm, "chat_structured", fake_llm)

def test_start_returns_question(monkeypatch):
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    import asyncio
    turn = asyncio.run(s.start())
    assert turn.evaluation is None and turn.question

def test_answer_evaluates_and_continues(monkeypatch):
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    import asyncio
    asyncio.run(s.start())
    turn = asyncio.run(s.answer("我的回答..."))
    assert turn.evaluation is not None
    assert turn.evaluation.score == 70

def test_empty_answer_triggers_tripwire(monkeypatch):
    import pytest
    _mock(monkeypatch)
    s = h.InterviewSession(InterviewConfig(), UserProfile())
    import asyncio
    asyncio.run(s.start())
    with pytest.raises(h.guardrails.Tripwire):
        asyncio.run(s.answer("   "))
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 写 `services/interview_harness.py`**
```python
import asyncio
from app.config import settings
from app.schemas.interview import (
    InterviewConfig, InterviewTurn, Evaluation, RecordRef, State,
)
from app.schemas.profile import UserProfile
from app.rag import store
from app.services import llm, guardrails

_STYLE_PROMPT = {
    "pressure": "你是高压型面试官，追问犀利、要求严谨。",
    "gentle": "你是温和引导型面试官，鼓励候选人展开。",
    "deep": "你是技术深挖型面试官，关注原理与边界。",
}

def _retrieve(config: InterviewConfig, query: str) -> list[RecordRef]:
    fmeta = {}
    if config.target_company:
        fmeta["company"] = config.target_company
    hits = asyncio.get_event_loop().run_until_complete(
        store.query_chunks(query, n=3, filter_meta=fmeta or None)
    )
    return [RecordRef(record_id=h["metadata"].get("record_id", h["id"]), snippet=h["text"][:200])
            for h in hits]

class InterviewSession:
    def __init__(self, config: InterviewConfig, profile: UserProfile):
        self.config = config
        self.profile = profile
        self.state = State.ASKING
        self.questions_asked = 0
        self.history: list[dict] = []

    def _system(self) -> str:
        p = self.profile
        ctx = (f"候选人：技能={p.skills}，年限={p.years}，目标岗位={p.target_role}，"
               f"目标公司={','.join(p.target_companies)}，薄弱点={p.weaknesses}，"
               f"市场环境={p.market_context}")
        return f"{_STYLE_PROMPT[self.config.interviewer_style]}\n{ctx}\n"
               f"严格按给定 JSON Schema 回复，必须包含 references（可空数组）。"

    async def start(self) -> InterviewTurn:
        self.state = State.ASKING
        refs = _retrieve(self.config, "开场自我介绍类问题")
        turn = await llm.chat_structured(
            self._system(),
            "请提出第一道面试问题（evaluation 为 null）。",
            InterviewTurn,
        )
        turn.references = refs
        await guardrails.output_guardrail(turn)
        self.questions_asked += 1
        self.history.append({"role": "assistant", "content": turn.question})
        return turn

    async def answer(self, user_msg: str) -> InterviewTurn:
        await guardrails.input_guardrail(user_msg)
        # 1) 评测上一轮回答
        eval_turn = await llm.chat_structured(
            self._system(),
            f"EVAL 用户回答：{user_msg}\n请对该回答评分并决定是否需要追问（ask_followup）。",
            InterviewTurn,
        )
        evaluation: Evaluation = eval_turn.evaluation or Evaluation(score=60)
        # 2) 决定下一步
        if self.questions_asked >= settings.max_questions:
            self.state = State.SUMMARY
            summary = await llm.chat_structured(
                self._system(),
                "面试结束，给出总体点评与改进建议（question 写总结，evaluation 写总评）。",
                InterviewTurn,
            )
            return summary
        follow_up = eval_turn.ask_followup
        if follow_up and eval_turn.followup_question:
            next_q = eval_turn.followup_question
            qtype = "follow_up"
        else:
            nxt = await llm.chat_structured(
                self._system(),
                "请提出下一道新的面试问题（evaluation 为 null）。",
                InterviewTurn,
            )
            next_q = nxt.question
            qtype = nxt.question_type
        out = InterviewTurn(question=next_q, question_type=qtype,
                            references=_retrieve(self.config, next_q),
                            evaluation=evaluation, ask_followup=bool(follow_up))
        await guardrails.output_guardrail(out)
        self.questions_asked += 1
        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": out.question})
        self.state = State.ASKING
        return out
```

> 注：`_retrieve` 中 `run_until_complete` 仅用于 MVP 内联同步调用；若测试在 async 上下文中可改为 `await store.query_chunks(...)`。可在 Task 13 整合测试中统一为 async 封装。

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/interview_harness.py && git commit -m "feat: interview harness (state machine + RAG-augmented agent loop + guardrails)"
```

---

### Task 11: 对话 Router（SSE 流式）

**Files:**
- Create/Modify: `backend/app/routers/chat.py`
- Test: `backend/tests/test_chat_router.py`

**Interfaces:**
- Produces:
  - `POST /api/chat/session` → JSON `InterviewTurn`（首题）
  - `POST /api/chat/message` → SSE 流：逐段 `data: {"type":"token","text":...}` + 末事件 `event: turn\ndata: <InterviewTurn JSON>`
- 会话存储：`SESSIONS: dict[str, InterviewSession]`（模块级，MVP 内存）

- [ ] **Step 1: 写测试（SSE 解析）**
```python
def test_session_and_message_sse(test_app, monkeypatch):
    import app.services.interview_harness as h
    import app.services.llm as llm
    from app.schemas.interview import InterviewTurn, Evaluation
    async def fake_llm(system, user, response_model, model=None):
        if "EVAL" in user:
            return InterviewTurn(question="下一题", question_type="technical",
                                 evaluation=Evaluation(score=75))
        return InterviewTurn(question="请做自我介绍", question_type="behavioral")
    monkeypatch.setattr(llm, "chat_structured", fake_llm)
    monkeypatch.setattr(h.store, "query_chunks", lambda *a, **k: [])

    s = test_app.post("/api/chat/session", json={"interviewer_style": "gentle"})
    assert s.status_code == 200
    sid = s.json()["session_id"]
    with test_app.stream("POST", f"/api/chat/message",
                         json={"session_id": sid, "message": "我的回答"}) as r:
        body = "".join(chunk.decode() for chunk in r.iter_lines())
    assert "event: turn" in body
    assert "question" in body
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 写 `routers/chat.py`**
```python
import uuid, json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.schemas.interview import InterviewConfig, InterviewTurn
from app.schemas.profile import UserProfile
from app.services.interview_harness import InterviewSession
from app.services import profile_service as psv

router = APIRouter(prefix="/api/chat", tags=["chat"])
SESSIONS: dict[str, InterviewSession] = {}

@router.post("/session")
async def create_session(config: InterviewConfig):
    profile = await psv.get_profile()
    sess = InterviewSession(config, profile)
    turn = await sess.start()
    sid = str(uuid.uuid4())
    SESSIONS[sid] = sess
    return {"session_id": sid, **turn.model_dump()}

def _split(text: str, size: int = 8):
    for i in range(0, len(text), size):
        yield text[i:i+size]

@router.post("/message")
async def send_message(payload: dict):
    sid = payload.get("session_id")
    sess = SESSIONS.get(sid)
    if not sess:
        return {"error": "unknown session"}
    turn = await sess.answer(payload.get("message", ""))

    async def event_stream():
        for piece in _split(turn.question):
            yield f"data: {json.dumps({'type':'token','text':piece}, ensure_ascii=False)}\n\n"
        yield f"event: turn\ndata: {turn.model_dump_json()}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit**
```bash
git add backend/app/routers/chat.py && git commit -m "feat: chat router with SSE streaming + session store"
```

---

### Task 12: 整合测试 + 可观测埋点

**Files:**
- Create: `backend/tests/test_integration.py`
- Modify: `backend/app/services/interview_harness.py`（补 trace 记录）

**Interfaces:**
- 端到端：导入题目 → 创建会话 → 多轮对话 → 校验每轮 `InterviewTurn` 可解析、带 `references`、状态机收敛到 SUMMARY。
- 可观测：每次 turn 记录 `{ts, session_id, input_len, output_len, score, retrieve_count, latency_ms, model}`（MVP 先打日志，后续接 eval harness）。

- [ ] **Step 1: 写整合测试**
```python
def test_end_to_end(test_app, monkeypatch):
    import app.services.interview_harness as h
    import app.services.llm as llm
    from app.schemas.interview import InterviewTurn, Evaluation, State
    import asyncio
    counter = {"n": 0}
    async def fake_llm(system, user, response_model, model=None):
        counter["n"] += 1
        if "EVAL" in user:
            return InterviewTurn(question="下一题", question_type="technical",
                                evaluation=Evaluation(score=70))
        return InterviewTurn(question=f"问题{counter['n']}", question_type="behavioral")
    monkeypatch.setattr(llm, "chat_structured", fake_llm)
    monkeypatch.setattr(h.store, "query_chunks", lambda *a, **k: [])

    s = test_app.post("/api/chat/session", json={})
    assert s.status_code == 200
    sid = s.json()["session_id"]
    for _ in range(5):
        with test_app.stream("POST", "/api/chat/message",
                             json={"session_id": sid, "message": "回答"}) as r:
            body = "".join(c.decode() for c in r.iter_lines())
        assert "event: turn" in body
    # 第 6 次应进入 SUMMARY（max_questions=5）
    with test_app.stream("POST", "/api/chat/message",
                         json={"session_id": sid, "message": "最后回答"}) as r:
        body = "".join(c.decode() for c in r.iter_lines())
    assert "总结" in body or "改进" in body
```

- [ ] **Step 2: 在 harness `answer()` 内增加可观测日志（最小实现）**
在 `answer()` 开头加 `import time; t0 = time.time()`，末尾：
```python
import logging
logging.info("turn ts=%s sid=? in=%d out=%d score=%s retrieve=%d ms=%.0f",
             time.time(), len(user_msg), len(out.question),
             out.evaluation.score if out.evaluation else None,
             len(out.references), (time.time()-t0)*1000)
```
（session_id 可在 Task 11 的 router 层记录；MVP 先打基础指标。）

- [ ] **Step 3: 运行全部测试**
Run: `cd backend && pytest -q` → 全部 PASS

- [ ] **Step 4: Commit**
```bash
git add backend && git commit -m "test: end-to-end interview flow + observability logging"
```

---

### Task 13: 运行说明与 README

**Files:**
- Create: `backend/README.md`

**Interfaces:** 供执行者/用户本地启动。

- [ ] **Step 1: 写 `backend/README.md`**
```markdown
# 面试训练 Agent — MVP 后端

## 启动
1. `cd backend`
2. `python -m venv .venv && .venv\Scripts\activate` (Windows) / `source .venv/bin/activate` (Linux)
3. `pip install -r requirements.txt`
4. 复制 `.env.example` 为 `.env` 并填入 `LLM_API_KEY` 与 `LLM_BASE_URL`
5. `uvicorn app.main:app --reload --port 8000`

## 接口速览
- POST /api/knowledge/records        录入面试记录（自动向量化）
- GET  /api/knowledge/records        检索（company / mindset 过滤）
- POST /api/knowledge/import         批量导入
- GET  /api/profile  | PUT /api/profile   用户画像
- POST /api/chat/session             开启模拟面试（返回首题）
- POST /api/chat/message             SSE 流式作答（token + 末事件 turn）

## 一致性保证（防漂移）
- 所有 Agent 回复遵循 `InterviewTurn` Pydantic Schema（instructor 解码层强制）
- 面试流程由 `InterviewSession` 确定性状态机驱动
- 输入/输出经 Guardrail + Tripwire 校验
```

- [ ] **Step 2: Commit**
```bash
git add backend/README.md && git commit -m "docs: MVP run instructions & API overview"
```

---

## 自检（Self-Review）

1. **Spec 覆盖**：知识库录入/检索/导入(FR-1,2 → Task 6)、RAG(向量化/检索 → Task 4,5)、用户画像(FR-3.1 → Task 7)、Agent 对话(FR-3.2-3.4 → Task 10,11)、Harness/防漂移(§3.3-3.4 → Task 9,10)、可观测(NFR-8 → Task 12) 均有对应任务。简历脱敏(④)、表达训练(⑤) 按计划属二期/三期，未含入 MVP，符合需求文档分期。
2. **Placeholder 扫描**：无 TBD/TODO；每个 Task 含真实代码与测试步骤。
3. **类型一致性**：`InterviewTurn / Evaluation / RecordRef / InterviewConfig / UserProfile / State / InterviewSession / Tripwire` 在 Task 3 定义并在 Task 9–12 一致引用；`create_record/list_records/delete_record/import_records`、`get_profile/update_profile`、`embed/chunk_text/add_chunks/query_chunks`、`chat_structured`、`input_guardrail/output_guardrail`、`start/answer` 签名前后一致。
4. **范围**：单 MVP 计划，可独立产出可运行后端，符合范围检查。

> 后续（非本计划）：二期 ④ 简历脱敏（自动标记 + 手动确认）、三期 ⑤ 文本表达训练评分、四期 ⑤ 语音 ASR 分析。
