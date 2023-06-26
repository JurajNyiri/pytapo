from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/images",
    tags=["images"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_images():
    logger.info("get_images")
    return {"get_images": "ok"}

