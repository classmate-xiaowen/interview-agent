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
