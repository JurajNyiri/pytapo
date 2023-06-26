# -*- coding: utf-8 -*-
import logging
import os
from datetime import datetime

import aiofiles
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from __version__ import __version__
from api.app.core.logging import Logger
from api.config import Settings

# import all routers
from api.app.routers.alarms import router as alarm_router
from api.app.routers.led import router as led_router
from api.app.routers.medias import router as medias_router
from api.app.routers.recordings import router as recording_router
from api.app.routers.settings import router as settings_router
from api.app.routers.devices import router as devices_router
from api.app.routers.client import router as client_router
from api.app.routers.detections import router as detection_router
from api.app.routers.home_assistant import router as home_assistant_router
from api.app.routers.motors import router as motor_router
from api.app.routers.presets import router as preset_router
from api.app.routers.images import router as image_router


startup_time = datetime.now()

settings = Settings()

logger = Logger(logging.INFO).get_logger()

swagger_ui_parameters = {
    "dom_id": "#swagger-ui",
    "layout": "BaseLayout",
    "deepLinking": True,
    "showExtensions": True,
    "showCommonExtensions": True,
    "syntaxHighlight.theme": "obsidian",
    "operationsSorter": "alpha",
    "configUrl": "/api/v1/openapi.json",
    "validatorUrl": None,
    "oauth2RedirectUrl": "http://localhost:8000/api/v1/docs/oauth2-redirect",
}

# Init app
app = FastAPI(
    title="pytapo ",
    description="Python FastAPI Tapo C200",
    version=__version__,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    swagger_ui_parameters=swagger_ui_parameters,
    redoc_url=None,
)


# add all routers to app
app.include_router(alarm_router)
app.include_router(led_router)
app.include_router(medias_router)
app.include_router(recording_router)
app.include_router(settings_router)
app.include_router(devices_router)
app.include_router(client_router)
app.include_router(detection_router)
app.include_router(home_assistant_router)
app.include_router(motor_router)
app.include_router(preset_router)
app.include_router(image_router)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    global startup_time
    startup_time = datetime.now()
    logger.info("Starting up application...")

    logger.info("Seeding database...")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application...")


@app.get("/health", tags=["Health"])
async def read_health():
    try:
        return {
            "status": "ok",
            "version": __version__,
            "uptime": (datetime.now() - startup_time).total_seconds(),
            "hostname": settings.HOST,
            "environment": settings.ENVIRONMENT,
        }
    except Exception as e:
        logger.error(f"Health check failed due to {str(e)}")
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/favicon.ico", tags=["Static"])
async def favicon():
    file_path = os.path.join(os.path.dirname(__file__), "static", "favicon.ico")
    async with aiofiles.open(file_path, mode="rb") as f:
        content = await f.read()
    return Response(content, media_type="image/x-icon")


@app.get("/", tags=["Root"])
def read_root():
    logger.info("read_root")
    return "PYTAPO API"
