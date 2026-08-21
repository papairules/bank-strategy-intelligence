from fastapi import APIRouter

from backend.app.api.v1.hiring.routes import router as hiring_router
from backend.app.api.v1.evidence.routes import router as evidence_router
from backend.app.api.v1.technology.routes import router as technology_router
from backend.app.api.v1.strategy.routes import router as strategy_router
from backend.app.api.v1.agents.routes import router as agents_router


router = APIRouter(prefix="/api/v1")
router.include_router(hiring_router)
router.include_router(technology_router)
router.include_router(evidence_router)
router.include_router(strategy_router)
router.include_router(agents_router)

__all__ = ["router"]
