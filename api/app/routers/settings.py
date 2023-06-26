from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_settings():
    logger.info("get_settings")
    return {"get_settings": "ok"}
