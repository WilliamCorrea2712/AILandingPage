"""
FastAPI application entry point.

Requirements: 9.1, 9.5, 9.6, 13.3, 13.5
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.exceptions import AppError
from app.middleware.rate_limit import RateLimitMiddleware

# Import routers
from app.api.auth import router as auth_router
from app.api.generate import router as generate_router
from app.api.logo import router as logo_router
from app.api.feedback import router as feedback_router
from app.api.train import router as train_router
from app.api.publish import router as publish_router
from app.api.projects import router as projects_router
from app.api.templates import router as templates_router
from app.api.analytics import router as analytics_router
from app.api.jobs import router as jobs_router

app = FastAPI(
    title="WTech Landing Page",
    description="Plataforma inteligente de geração de landing pages com IA.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS â€” allow all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (only when Redis is available)
app.add_middleware(RateLimitMiddleware)


# Global exception handler â€” returns standardised ErrorResponse
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "Ocorreu um erro interno. Tente novamente mais tarde.",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


# Register routers
app.include_router(auth_router)
app.include_router(generate_router)
app.include_router(logo_router)
app.include_router(feedback_router)
app.include_router(train_router)
app.include_router(publish_router)
app.include_router(projects_router)
app.include_router(templates_router)
app.include_router(analytics_router)
app.include_router(jobs_router)

# Serve uploaded logos as static files
from pathlib import Path as _Path
_Path("uploads/logos").mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "timestamp": datetime.now(tz=timezone.utc).isoformat()}


