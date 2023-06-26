from fastapi import APIRouter, Depends

from api.app.core.logging import Logger
from pytapo.error import AlarmException
from pytapo.settings.alarm import AlarmInterface

logger = Logger().get_logger()

router = APIRouter(
    prefix="/alarms",
    tags=["alarms"],
    responses={404: {"description": "Not found"}},
)

# Assuming you have a function to create AlarmInterface instances
def get_alarm_interface():
    execute_function = None # Replace with actual function
    perform_request = None # Replace with actual function
    child_id = None # Replace with actual child_id
    return AlarmInterface(execute_function, perform_request, child_id)

@router.get("/")
async def get_alarms():
    logger.info("get_alarms")
    return {"get_alarms": "ok"}

@router.post("/start_manual_alarm")
async def start_manual_alarm(alarm: AlarmInterface = Depends(get_alarm_interface)):
    return alarm.start_manual_alarm()

@router.post("/stop_manual_alarm")
async def stop_manual_alarm(alarm: AlarmInterface = Depends(get_alarm_interface)):
    return alarm.stop_manual_alarm()

@router.post("/set_alarm/{enabled}/{sound_enabled}/{light_enabled}")
async def set_alarm(enabled: bool, sound_enabled: bool, light_enabled: bool, alarm: AlarmInterface = Depends(get_alarm_interface)):
    try:
        return alarm.set_alarm(enabled, sound_enabled, light_enabled)
    except AlarmException as e:
        return {"error": str(e)}

@router.get("/get_alarm")
async def get_alarm(alarm: AlarmInterface = Depends(get_alarm_interface)):
    return alarm.get_alarm()

@router.get("/get_alarm_config")
async def get_alarm_config(alarm: AlarmInterface = Depends(get_alarm_interface)):
    return alarm.get_alarm_config()
