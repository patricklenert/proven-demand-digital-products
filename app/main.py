"""
Proven Demand FastAPI application.
Core intelligence engine for Supply vs Demand Gap Score computation.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.api import pipeline, opportunities, summary
# Import Celery tasks to register them
from app.services import tasks  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes database tables on startup.
    """
    # Startup: Create database tables
    init_db()
    yield
    # Shutdown: Cleanup if needed (currently none)


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligence engine for computing Supply vs Demand Gap Scores across digital product marketplaces",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware (useful for Windmill.dev and future integrations)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(pipeline.router)
app.include_router(opportunities.router)
app.include_router(summary.router)


@app.get("/")
async def root():
    """
    Root endpoint for health checks.
    
    Returns:
        API name and status
    """
    return {
        "name": settings.APP_NAME,
        "status": "operational",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        Health status
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
