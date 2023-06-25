# -*- coding: utf-8 -*-
import logging
import os
from datetime import datetime

import aiofiles
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from __version__ import __version__

# import all routers
from app.routers import article, company, news, users

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

limiter = Limiter(key_func=get_remote_address)

# Init app
app = FastAPI(
    title="AI News Tracker API",
    description="AI News Tracker API",
    version=__version__,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    swagger_ui_parameters=swagger_ui_parameters,
    redoc_url=None,
)

#  Rate Limiting
app.state.limiter = limiter
app.add_exception_handler(HTTPException, _rate_limit_exceeded_handler)

# add all routers to app
app.include_router(users.router)
app.include_router(company.router)
app.include_router(article.router)
app.include_router(news.router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# add cache middleware to app
redis_instance = RedisDB()


@app.on_event("startup")
async def startup():
    global startup_time
    startup_time = datetime.now()
    logger.info("Starting up application...")

    try:
        FastAPICache.init(
            backend=RedisBackend(redis_instance._connection), prefix="redis-cache"
        )
    except Exception:
        logger.error("Redis server not available")
        FastAPICache.init(InMemoryBackend(), prefix="inmemory-cache")

    logger.info("Seeding database...")
    #seed_companies = await CompanySeeder().seed_companies()
    seed_news = await NewsSeeder().seed_news()
    

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application...")
    redis_instance.close()
    MongoDB().close()


def get_service_health(check_function, get_info_function, service_name_function):
    try:
        is_healthy = check_function()
        service_info = get_info_function() or {
            "version": "unknown",
            "uptime": "unknown",
        }
        uptime = service_info.get("uptime", "unknown")
        service_name = service_name_function() or service_name_function or "Unknown"
        if (
            "uptime" in service_info
            and service_info["uptime"] is not None
            and service_info["uptime"] != "unknown"
        ):
            service_info["uptime"] = (
                datetime.now() - datetime.fromtimestamp(service_info["uptime"])
            ).total_seconds()
        else:
            service_info["uptime"] = "unknown"
    except Exception as e:
        is_healthy = False
        service_info = {"version": "unknown", "uptime": "unknown"}
        service_name = "Unknown"

    version = service_info.get("version", "unknown")
    uptime = service_info.get("uptime", "unknown")

    return {
        "status": "ok" if is_healthy else "unavailable",
        "version": version,
        "uptime": uptime,
        "hostname": service_name,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health", tags=["Health"])
async def read_health():
    try:
        prometheus_health = get_service_health(
            check_prometheus_health,
            lambda: {
                "version": "2.26.0",
                "uptime": (datetime.now() - startup_time).total_seconds(),
            },
            "localhost",
        )

        redis_health = get_service_health(
            redis_instance.check_connection,
            redis_instance.get_info,
            redis_instance.get_hostname(),
        )

        mongodb_instance = MongoDB()

        mongodb_health = get_service_health(
            mongodb_instance.check_connection,
            mongodb_instance.get_info,
            mongodb_instance.get_hostname(),
        )

        return {
            "status": "ok",
            "version": __version__,
            "uptime": (datetime.now() - startup_time).total_seconds(),
            "hostname": settings.HOST,
            "environment": settings.ENVIRONMENT,
            "dependencies": {
                "redis": redis_health,
                "mongodb": mongodb_health,
                "prometheus": prometheus_health,
            },
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


@limiter.limit("5/minute")
@app.get("/", tags=["Root"])
@cache(expire=60)
def read_root():
    logger.info("AI News Tracker API")
    return "AI News Tracker API"


if __name__ == "__main__":
    Instrumentator().instrument(app).expose(app)