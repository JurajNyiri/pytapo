from fastapi import APIRouter

from api.app.core.logging import Logger


logger = Logger().get_logger()

router = APIRouter(
    prefix="/recordings",
    tags=["recordings"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_recordings():
    logger.info("get_recordings")
    return {"get_recordings": "ok"}
