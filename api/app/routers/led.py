from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/led",
    tags=["led"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_led():
    logger.info("get_led")
    return {"get_led": "ok"}