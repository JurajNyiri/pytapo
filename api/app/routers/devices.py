from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/devices",
    tags=["devices"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_devices():
    logger.info("get_devices")
    return {"get_devices": "ok"}
