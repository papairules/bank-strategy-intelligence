from fastapi import APIRouter

from backend.app.api.v1.hiring.routes import router as hiring_router


router = APIRouter(prefix="/api/v1")
router.include_router(hiring_router)

__all__ = ["router"]
