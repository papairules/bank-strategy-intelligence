from fastapi import FastAPI

from backend.app.api.v1 import router as api_v1_router

app = FastAPI(
    title="Bank Strategy Intelligence API",
    description="AI-powered intelligence platform for banking strategy and investment analysis.",
    version="0.1.0",
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
