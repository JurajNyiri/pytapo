from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/motors",
    tags=["motors"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_motors():
    logger.info("get_motors")
    return {"get_motors": "ok"}

