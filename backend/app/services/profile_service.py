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
                          market_context=row.market_context, resume_text=row.resume_text or "")


async def update_profile(data: UserProfile) -> UserProfile:
    async with SessionLocal() as s:
        row = await s.get(UserProfileRow, 1)
        if not row:
            row = UserProfileRow()
        row.skills = data.skills; row.years = data.years; row.target_role = data.target_role
        row.target_companies = data.target_companies; row.weaknesses = data.weaknesses
        row.market_context = data.market_context; row.resume_text = data.resume_text
        s.add(row); await s.commit(); await s.refresh(row)
        return UserProfile(skills=row.skills, years=row.years, target_role=row.target_role,
                          target_companies=row.target_companies or [], weaknesses=row.weaknesses,
                          market_context=row.market_context, resume_text=row.resume_text or "")
