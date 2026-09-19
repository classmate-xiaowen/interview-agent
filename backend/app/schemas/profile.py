from pydantic import BaseModel


class UserProfile(BaseModel):
    skills: str = ""
    years: int = 0
    target_role: str = ""
    target_companies: list[str] = []
    weaknesses: str = ""
    market_context: str = ""
    resume_text: str = ""   # 脱敏版简历（原文永不入库，仅脱敏版可持久化）
