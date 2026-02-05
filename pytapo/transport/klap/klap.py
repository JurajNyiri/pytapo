import json
from kasa.exceptions import (
    AuthenticationError,
)
from kasa import DeviceConfig, Credentials
from kasa.transports import KlapTransportV2, KlapTransport
from ...const import EncryptionMethod


class Klap:

    def __init__(
        self,
        host: str,
        controlPort: int,
        user: str,
        password: str,
        KLAPVersion: int = None,
    ):
        print("PASSED KLAP:")
        print(KLAPVersion)
        self.host = host
        self.controlPort = controlPort
        self.user = user
        self.password = password
        self.klapTransport = None

        if KLAPVersion is not None:
            self.KLAPVersion = KLAPVersion
        else:
            self.KLAPVersion = None

    async def authenticate(self, retry=False):
        self.debugLog("Klap: authenticate called")
        if self.klapTransport is None:
            self.debugLog("Klap: authenticate running...")
            self.debugLog("Klap: self.klapTransport is None")
            if self.KLAPVersion is None:
                self.debugLog("Klap: self.KLAPVersion is None")
                try:
                    self.debugLog("Klap: Trying to use Klap version 1...")
                    await self._initiateKlapTransport(1)
                    self.debugLog("Klap: Determined Klap version 1.")
                    self.KLAPVersion = 1
                except AuthenticationError as err:
                    self.debugLog(f"Klap: Klap version 1 failed: {err}")
                    try:
                        self.debugLog("Klap: Trying to use Klap version 2...")
                        await self._initiateKlapTransport(2)
                        self.KLAPVersion = 2
                        self.debugLog("Klap: Determined Klap version 2.")
                    except AuthenticationError:
                        raise Exception("Invalid authentication data")
                    except Exception as err:
                        raise Exception("PyTapo KLAP Error #2: " + str(err))
                except Exception as err:
                    raise Exception("PyTapo KLAP Error #3: " + str(err))
            else:
                self.debugLog(
                    f"Klap: self.KLAPVersion is {self.KLAPVersion}. Initiating transport..."
                )
                if self.KLAPVersion == 1:
                    try:
                        await self._initiateKlapTransport(1)
                    except AuthenticationError:
                        raise Exception("Invalid authentication data")
                    except Exception as err:
                        raise Exception("PyTapo KLAP Error #4: " + str(err))
                elif self.KLAPVersion == 2:
                    try:
                        await self._initiateKlapTransport(2)
                    except AuthenticationError:
                        raise Exception("Invalid authentication data")
                    except Exception as err:
                        raise Exception("PyTapo KLAP Error #5: " + str(err))
        return True

    async def send(self, request, retry=0):
        try:
            if self.klapTransport is None:
                await self.authenticate()
            response = await self.klapTransport.send(json.dumps(request))
            return response
        except Exception as err:
            if (
                "Response status is 403, Request was" in str(err)
                or "Response status is 400, Request was" in str(err)
                or "Server disconnected" in str(err)
            ):
                raise Exception("PyTapo KLAP Error #6: " + str(err))

            self.debugLog("Retrying request... Error: " + str(err))
            if retry < 5:
                await self.authenticate()
                return await self.send(request, retry + 1)
            else:
                raise Exception("PyTapo KLAP Error #1: " + str(err))
        finally:
            if self.klapTransport is not None:
                await self.klapTransport.close()

    def getEncryptionMethod():
        return EncryptionMethod.SHA256

    async def close(self):
        await self.klapTransport.close()

    async def _initiateKlapTransport(self, version=1):
        try:
            if self.klapTransport is None:
                creds = Credentials(self.user, self.password)
                config = DeviceConfig(
                    self.host, port_override=self.controlPort, credentials=creds
                )
                if version == 1:
                    transport = KlapTransport(config=config)
                elif version == 2:
                    transport = KlapTransportV2(config=config)
                await transport.perform_handshake()
                self.klapTransport = transport
                return self.klapTransport
        finally:
            await transport.close()

    def debugLog(self, msg: str):
        pass

    def warnLog(self, msg: str):
        pass
