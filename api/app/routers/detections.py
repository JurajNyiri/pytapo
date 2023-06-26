from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/detections",
    tags=["detections"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_detections():
    logger.info("get_detections")
    return {"get_detections": "ok"}
