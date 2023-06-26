from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/home_assistant",
    tags=["home_assistant"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_home_assistant():
    logger.info("get_home_assistant")
    return {"get_home_assistant": "ok"}