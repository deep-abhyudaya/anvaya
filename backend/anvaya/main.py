"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from anvaya.config import settings
from anvaya.db import init_db
from anvaya.logging import configure_logging, get_logger
from anvaya.startuped_signals import emit_api_request_signal


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    logger = get_logger("anvaya.main")
    init_db()
    logger.info("anvaya.startup", database=settings.database_url, llm=settings.is_llm_enabled())
    yield
    logger.info("anvaya.shutdown")


app = FastAPI(
    title="ANVAYA",
    description="Autonomous Cyber SOC Platform",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = list(settings.cors_origins)
allow_credentials = True

frontend_origin = (
    os.environ.get("BETTER_AUTH_URL")
    or os.environ.get("NEXT_PUBLIC_AUTH_URL")
    or "http://localhost:3000"
)
if frontend_origin not in cors_origins:
    cors_origins.append(frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    emit_api_request_signal(request.method, request.url.path, response.status_code)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = get_logger("anvaya.main")
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "anvaya", "version": "0.1.0"}


from anvaya.routers import (  # noqa: E402
    agent,
    audit,
    blastscope,
    datasets,
    demo,
    detections,
    graph,
    incidents,
    metrics,
    models,
    projects,
    replay,
    rules,
    sentinel,
    simulation,
    telemetry,
    whatif,
)

prefix = "/api/v1"
app.include_router(incidents.router, prefix=prefix, tags=["incidents"])
app.include_router(telemetry.router, prefix=prefix, tags=["telemetry"])
app.include_router(detections.router, prefix=prefix, tags=["detections"])
app.include_router(rules.router, prefix=prefix, tags=["rules"])
app.include_router(replay.router, prefix=prefix, tags=["replay"])
app.include_router(sentinel.router, prefix=prefix, tags=["sentinel"])
app.include_router(blastscope.router, prefix=prefix, tags=["blastscope"])
app.include_router(whatif.router, prefix=prefix, tags=["whatif"])
app.include_router(audit.router, prefix=prefix, tags=["audit"])
app.include_router(graph.router, prefix=prefix, tags=["graph"])
app.include_router(metrics.router, prefix=prefix, tags=["metrics"])
app.include_router(models.router, prefix=prefix, tags=["models"])
app.include_router(projects.router, prefix=prefix, tags=["projects"])
app.include_router(datasets.router, prefix=prefix, tags=["datasets"])
app.include_router(demo.router, prefix=prefix, tags=["demo"])
app.include_router(simulation.router, prefix=prefix, tags=["simulation"])
app.include_router(agent.router, prefix=prefix, tags=["agent"])
