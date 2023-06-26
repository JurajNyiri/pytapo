from fastapi import APIRouter

from api.app.core.logging import Logger

logger = Logger().get_logger()

router = APIRouter(
    prefix="/presets",
    tags=["presets"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_presets():
    logger.info("get_presets")
    return {"get_presets": "ok"}
