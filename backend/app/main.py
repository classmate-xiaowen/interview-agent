from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init_db
from app.rag import store
from app.services import knowledge_service
from app.routers import knowledge, profile, chat, resume

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # embedding 模型变更后，旧集合残留的向量维度可能不匹配（如 MiniLM 384 vs 当前模型）。
    # 检测命中则重建集合并重新索引知识库，避免 add/query 维度冲突且保证检索可用。
    try:
        if await store.check_dimension_mismatch():
            print("[startup] 检测到向量维度不匹配，重建集合并重新索引知识库…")
            await store.reset_collection()
            await knowledge_service.reindex_all()
            print("[startup] 知识库重新索引完成")
    except Exception as e:
        print(f"[startup] 向量自愈失败（不影响启动，可在导入页重新导入）: {e}")
    yield

app = FastAPI(title="Interview Agent MVP", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(knowledge.router)
app.include_router(profile.router)
app.include_router(chat.router)
app.include_router(resume.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
