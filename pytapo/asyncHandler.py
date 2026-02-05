import asyncio


class AsyncHandler:
    def __init__(self, hass):
        self.hass = hass
        self._loop = None
        pass

    def executeAsyncExecutorJob(self, job, *args):
        if self.hass is None:
            # reuse a dedicated loop so kasa aiohttp sessions stay alive between calls
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(self._loop)
                return self._loop.run_until_complete(job(*args))
            finally:
                asyncio.set_event_loop(None)
        else:
            return asyncio.run_coroutine_threadsafe(job(*args), self.hass.loop).result()
