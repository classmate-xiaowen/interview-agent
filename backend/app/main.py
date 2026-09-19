from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init_db
from app.routers import knowledge, profile, chat, resume

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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
