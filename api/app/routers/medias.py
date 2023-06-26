from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/medias",
    tags=["medias"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_medias():
    logger.info("get_medias")
    return {"get_medias": "ok"}

