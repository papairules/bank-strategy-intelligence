from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1 import router as api_v1_router
from backend.app.config import HiringSettings

app = FastAPI(
    title="Bank Strategy Intelligence API",
    description="AI-powered intelligence platform for banking strategy and investment analysis.",
    version="0.1.0",
)
settings = HiringSettings()
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
app.include_router(api_v1_router)


@app.get("/")
def root():
    return {
        "name": "Bank Strategy Intelligence API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
