import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure project root is in sys.path so backend imports work from any working directory
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.app.core.config import settings
from backend.app.db.session import init_db
from backend.app.api.routes import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables and seed Persona 1
    await init_db()
    yield
    # Shutdown logic if any


app = FastAPI(
    title=settings.APP_NAME,
    description="Text-First AI Companionship Platform — Phase 1 Prototype",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV, "version": "v8.0"}

# Mount API routes
app.include_router(api_router)

# Mount Frontend static files if directory exists
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", getattr(settings, "PORT", 8000)))
    print(f"\n🚀 Starting AI Companion Phase 1 Prototype on port {port}...")
    print(f"📍 Web App: http://127.0.0.1:{port}")
    print(f"📖 API Docs: http://127.0.0.1:{port}/docs\n")
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port, reload=True)

