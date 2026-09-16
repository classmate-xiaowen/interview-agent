from pydantic import BaseModel


class UserProfile(BaseModel):
    skills: str = ""
    years: int = 0
    target_role: str = ""
    target_companies: list[str] = []
    weaknesses: str = ""
    market_context: str = ""
