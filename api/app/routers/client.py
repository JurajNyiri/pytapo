from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/connect",
    tags=["client"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def connect():
    logger.info("connect")
    return {"connect": "ok"}