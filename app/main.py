"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.payments import router as payments_router
from app.api.referrals import router as referrals_router
from app.api.router import router as api_router
from app.api.tariffs import router as tariffs_router
from app.config import get_settings
from app.models.database import init_db
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events handler."""
    logger.info("Starting Mutual Followers Analyzer API...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    yield

    logger.info("Shutting down Mutual Followers Analyzer API...")


settings = get_settings()

app = FastAPI(
    title="Mutual Followers Analyzer API",
    description="API for analyzing Instagram mutual followers",
    version="0.2.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(api_router, prefix="/api/v1")
app.include_router(tariffs_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(referrals_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "mutual-followers-analyzer"}
