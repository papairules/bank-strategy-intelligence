from fastapi import FastAPI

app = FastAPI(
    title="Bank Strategy Intelligence API",
    description="AI-powered intelligence platform for banking strategy and investment analysis.",
    version="0.1.0",
)


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