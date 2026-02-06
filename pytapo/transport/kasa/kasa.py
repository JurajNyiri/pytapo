import logging
import ssl
from contextlib import suppress
from ...const import EncryptionMethod, MAX_LOGIN_RETRIES
from kasa import Device, DeviceConfig, DeviceError, Discover, Credentials

from kasa.deviceconfig import (
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.exceptions import (
    AuthenticationError,
    SmartErrorCode,
    TimeoutError as KasaTimeoutError,
)


# Supress Error messages, we handle them internally and log if necessary
class SuppressPythonKasaLogs(logging.Filter):
    def filter(self, record):
        return (
            "Response status is 403" not in record.getMessage()
            and "Server disconnected" not in record.getMessage()
            and "Response status is 400, Request was" not in record.getMessage()
        )


class Kasa:
    def __init__(self, host: str, controlPort: int, user: str, password: str):
        logger = logging.getLogger("kasa.transports.klaptransport")
        logger.addFilter(SuppressPythonKasaLogs())
        self.host = host
        self.controlPort = controlPort
        self.user = user
        self.password = password
        self.dev = None
        self._loop = None
        self._kasa_ssl_fallback = False
        self._kasa_ssl_fallback_context = None
        self._kasa_ssl_default_context = None
        self._kasa_ssl_probe_done = False

    async def send(self, request, retry=0):
        """Send a smart request via kasa protocol.query (with format translation)."""
        self.debugLog(f"send called, retry: {retry}")
        await self.authenticate()
        self.debugLog("Converting request:")
        self.debugLog(request)

        proto = self.dev.protocol
        kasa_request = request
        request_method = None
        raw_response = None

        if isinstance(request, dict) and "method" in request:
            request_method = request.get("method")
            if request_method == "multipleRequest":
                params = request.get("params") or {}
                kasa_request = {"multipleRequest": params}
            elif request_method in {"get", "set", "do"}:
                payload = {k: v for k, v in request.items() if k != "method"}
                if "params" in payload and len(payload) == 1:
                    payload = payload["params"]
                kasa_request = {request_method: payload}
            else:
                if "params" in request and len(request) == 2:
                    kasa_request = {request_method: request["params"]}
                else:
                    payload = {k: v for k, v in request.items() if k != "method"}
                    kasa_request = (
                        {request_method: payload} if payload else request_method
                    )

        self.debugLog("Converted query:")
        self.debugLog(kasa_request)

        original_send = proto._transport.send

        self.debugLog("Overriding proto._transport.send...")

        # Capture original error codes
        async def send_wrapper(payload):
            nonlocal raw_response
            raw_response = await original_send(payload)
            self.debugLog(f"Raw response: {raw_response}")
            return raw_response

        proto._transport.send = send_wrapper

        self.debugLog("Sending query...")
        try:
            result = await proto.query(kasa_request)
        except AuthenticationError as err:
            self.debugLog(f"kasa query failed (auth): {err}")
            if retry < MAX_LOGIN_RETRIES:
                self.debugLog("Resetting transport and retrying request.")
                reset = getattr(proto._transport, "reset", None)
                if reset is not None:
                    self.debugLog("Requesting reset.")
                    await reset()
                else:
                    self.debugLog("Recreating connection.")
                    await self.close()
                return await self.send(request, retry + 1)
            await self.close()
            raise Exception("Invalid authentication data") from err
        except DeviceError as err:
            code = getattr(err, "error_code", None)
            self.debugLog(f"kasa query failed (DeviceError), code: {code}, err: {err}")

            if code == SmartErrorCode.INTERNAL_UNKNOWN_ERROR:
                if isinstance(raw_response, dict) and "error_code" in raw_response:
                    self.debugLog(
                        f"Captured raw device error: {raw_response.get('error_code')}"
                    )
                    return raw_response
            if code == SmartErrorCode.DEVICE_BLOCKED:
                await self.close()
                raise Exception(f"Temporary Suspension: {str(err)}") from err
            if retry < MAX_LOGIN_RETRIES:
                self.debugLog("Resetting transport and retrying request.")
                reset = getattr(proto._transport, "reset", None)
                if reset is not None:
                    self.debugLog("Requesting reset.")
                    await reset()
                else:
                    self.debugLog("Recreating connection.")
                    await self.close()
                return await self.send(request, retry + 1)
            await self.close()
            raise
        except Exception as err:
            self.debugLog(f"kasa query failed: {err}")
            # todo: this might be sometimes needed on stopiteration error but was solved by using executeFunction instead for a call
            # if self._is_kasa_stop_iteration(err) and isinstance(raw_response, dict):
            #    self.debugLog(
            #        f"Caught kasa error {err}, and raw response is available. Returning."
            #    )
            #    return raw_response
            if self._is_kasa_ssl_handshake_failure(err):
                if not self._kasa_ssl_fallback:
                    self.warnLog(
                        f"Creating unsecure SSL context because of unexpected encryption error: {err}"
                    )
                    await self._log_kasa_ssl_details(
                        err,
                        "query",
                        context=getattr(proto._transport, "_ssl_context", None),
                    )
                self._kasa_ssl_fallback = True
                self._apply_kasa_ssl_fallback_to_transport()
            if retry < MAX_LOGIN_RETRIES:
                self.debugLog("Resetting transport and retrying request.")
                reset = getattr(proto._transport, "reset", None)
                if reset is not None:
                    self.debugLog("Requesting reset.")
                    await reset()
                else:
                    self.debugLog("Recreating connection.")
                    await self.close()
                return await self.send(request, retry + 1)
            await self.close()
            raise
        finally:
            proto._transport.send = original_send

        converted = result
        if request_method == "multipleRequest":
            multi_result = (
                result.get("multipleRequest") if isinstance(result, dict) else None
            )
            if multi_result is not None:
                converted = {"error_code": 0, "result": multi_result}
        elif request_method in {"get", "set", "do"}:
            if request_method == "set":
                converted = {"error_code": 0}
            elif request_method == "get":
                data = result.get("get", {}) if isinstance(result, dict) else {}
                if isinstance(data, dict):
                    converted = {"error_code": 0, **data}
                else:
                    converted = {"error_code": 0}
            else:
                data = result.get("do", {}) if isinstance(result, dict) else {}
                if isinstance(data, dict):
                    converted = (
                        data if "error_code" in data else {"error_code": 0, **data}
                    )
                else:
                    converted = {"error_code": 0}
        elif isinstance(result, dict) and request_method and request_method in result:
            converted = {"error_code": 0, "result": result[request_method]}

        self.debugLog(f"Result: {converted}")
        return converted

    async def authenticate(self, retry=False):
        if self.dev is None:
            self.debugLog("Creating new Kasa-Tapo instance...")
            creds = Credentials(self.user, self.password)

            direct_connection_options = [
                DeviceConnectionParameters(
                    DeviceFamily.SmartIpCamera,
                    DeviceEncryptionType.Aes,
                    https=True,
                )
            ]
            try:
                self.dev = await Discover.discover_single(self.host, credentials=creds)
            except KasaTimeoutError as err:
                self.debugLog(
                    "kasa discover_single timed out, trying direct connect..."
                )
                self.warnLog(
                    f"Failed to automatically discover details of device {self.host}. Attempting to connect directly by trying all authentication methods."
                )
                for encrypt_type in DeviceEncryptionType:
                    if encrypt_type is DeviceEncryptionType.Klap:
                        continue
                    for https in (True, False):
                        if encrypt_type is DeviceEncryptionType.Aes and https is True:
                            continue
                        direct_connection_options.append(
                            DeviceConnectionParameters(
                                DeviceFamily.SmartIpCamera,
                                encrypt_type,
                                https=https,
                            )
                        )

                async def try_direct_connect():
                    last_err = None
                    for conn_params in direct_connection_options:
                        self.debugLog(
                            "kasa direct connect attempt: "
                            f"encrypt={conn_params.encryption_type.value} "
                            f"https={conn_params.https} "
                            f"device_family={conn_params.device_family}"
                        )
                        dev = None
                        try:
                            config = DeviceConfig(
                                host=self.host,
                                port_override=self.controlPort,
                                timeout=10,
                                credentials=creds,
                                connection_type=conn_params,
                            )
                            dev = await self._kasa_connect_without_update(config)
                            try:
                                await dev.protocol.query(
                                    {
                                        "getDeviceInfo": {
                                            "device_info": {"name": ["basic_info"]}
                                        }
                                    }
                                )
                                return dev
                            except Exception as probe_err:
                                if (
                                    self._is_kasa_ssl_handshake_failure(probe_err)
                                    and not self._kasa_ssl_fallback
                                ):
                                    self.warnLog(
                                        "Creating unsecure SSL context because of "
                                        f"unexpected encryption error on direct connect probe: {probe_err}"
                                    )
                                    await self._log_kasa_ssl_details(
                                        probe_err,
                                        "direct connect probe",
                                        context=getattr(
                                            dev.protocol._transport,
                                            "_ssl_context",
                                            None,
                                        ),
                                    )
                                    self._kasa_ssl_fallback = True
                                    try:
                                        dev.protocol._transport._ssl_context = (
                                            self._get_kasa_ssl_fallback_context()
                                        )
                                    except Exception as apply_err:
                                        self.warnLog(
                                            f"Failed to apply SSL context: {apply_err}"
                                        )
                                    await dev.protocol.query(
                                        {
                                            "getDeviceInfo": {
                                                "device_info": {"name": ["basic_info"]}
                                            }
                                        }
                                    )
                                    return dev
                                raise
                        except AuthenticationError as err:
                            if dev is not None:
                                with suppress(Exception):
                                    await dev.protocol.close()
                            raise err
                        except DeviceError as err:
                            if dev is not None:
                                with suppress(Exception):
                                    await dev.protocol.close()
                            code = getattr(err, "error_code", None)
                            self.debugLog(
                                f"kasa direct connect probe failed (device error): {err}"
                            )
                            await self.close()
                            if code == SmartErrorCode.DEVICE_BLOCKED:
                                raise Exception(
                                    f"Temporary Suspension: {str(err)}"
                                ) from err
                            raise
                        except Exception as err:
                            if dev is not None:
                                with suppress(Exception):
                                    await dev.protocol.close()
                            self.debugLog(err)
                            last_err = err
                    if last_err is not None:
                        raise last_err
                    return None

                try:
                    self.dev = await try_direct_connect()
                except AuthenticationError as err:
                    self.debugLog(err)
                    await self.close()
                    raise Exception("Invalid authentication data") from err
                except Exception as direct_err:
                    self.debugLog(direct_err)
                    if "Temporary Suspension" in str(direct_err):
                        raise direct_err
                    raise Exception(
                        "Failed to establish a new connection: "
                        f"{str(err)} (direct connect failed: {direct_err})"
                    ) from direct_err
            except Exception as err:
                self.debugLog(err)
                if retry is False:
                    self.debugLog("Ensure authenticated failed, retrying.")
                    self.debugLog("Resetting kasa and retrying request.")
                    await self.close()
                    return await self.authenticate(True)
                else:
                    await self.close()
                    raise err
            if self.dev is None:
                raise Exception("Device not found via python-kasa")
            self.debugLog(
                f"kasa device: host={self.host} proto={type(self.dev.protocol).__name__}"
            )
            self._log_kasa_connection_info()
            if self._kasa_ssl_fallback:
                self._apply_kasa_ssl_fallback_to_transport()

    def getEncryptionMethod(self):
        if self.dev and getattr(self.dev, "config", None):
            ct = getattr(self.dev.config, "connection_type", None)
            login_version = getattr(ct, "login_version", None) if ct else None
            if login_version is not None and login_version < 2:
                return EncryptionMethod.MD5
        return EncryptionMethod.SHA256

    def _log_kasa_connection_info(self):
        ct = getattr(getattr(self.dev, "config", None), "connection_type", None)
        transport = getattr(self.dev, "protocol", None)
        transport_impl = getattr(transport, "_transport", None)

        device_info = {
            "alias": getattr(self.dev, "alias", None),
            "model": getattr(self.dev, "model", None),
            "mac": getattr(self.dev, "mac", None),
        }
        hw_info = getattr(self.dev, "hw_info", {}) or {}
        device_info["fw"] = hw_info.get("sw_ver") or hw_info.get("fw_ver")

        self.debugLog(f"kasa device: {device_info}")
        self.debugLog(f"kasa chosen encryption: {self.getEncryptionMethod()}")

        if ct:
            fields = {
                "device_family": getattr(ct, "device_family", None),
                "encryption_type": getattr(ct, "encryption_type", None),
                "https": getattr(ct, "https", None),
                "login_version": getattr(ct, "login_version", None),
                "http_port": getattr(ct, "http_port", None),
            }
            self.debugLog(
                f"kasa connection_type: {fields}, "
                f"protocol={type(transport).__name__}, "
                f"transport={type(transport_impl).__name__ if transport_impl else None}"
            )
        else:
            self.debugLog("kasa connection_type: <unavailable>")

    def _is_kasa_ssl_handshake_failure(self, err):
        for ex in self._iter_exception_chain(err):
            msg = str(ex).lower()
            if "sslv3_alert_handshake_failure" in msg or "handshake failure" in msg:
                return True
            if isinstance(ex, ssl.SSLError):
                reason = getattr(ex, "reason", None)
                if reason and "handshake_failure" in str(reason).lower():
                    return True
        return False

    def _is_kasa_stop_iteration(self, err):
        for ex in self._iter_exception_chain(err):
            if isinstance(ex, StopIteration):
                return True
            if isinstance(ex, RuntimeError) and "StopIteration" in str(ex):
                return True
        return False

    def _create_kasa_default_ssl_context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with suppress(Exception):
            from kasa.transports.sslaestransport import SslAesTransport

            context.set_ciphers(SslAesTransport.CIPHERS)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def _get_kasa_default_ssl_context(self):
        if self._kasa_ssl_default_context is None:
            self._kasa_ssl_default_context = self._create_kasa_default_ssl_context()
        return self._kasa_ssl_default_context

    def _create_kasa_unsecure_ssl_context(self):
        self.debugLog("_create_kasa_unsecure_ssl_context called")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with suppress(Exception):
            context.minimum_version = ssl.TLSVersion.TLSv1
        with suppress(Exception):
            context.options |= ssl.OP_LEGACY_SERVER_CONNECT
        with suppress(Exception):
            context.set_ciphers("ALL:@SECLEVEL=0")
        return context

    async def _log_kasa_ssl_details(self, err, phase, context=None):
        if self._kasa_ssl_probe_done:
            return
        self._kasa_ssl_probe_done = True
        try:
            self.warnLog(f"kasa ssl details ({phase}): {err}")
            base_context = context or self._get_kasa_default_ssl_context()
            default_ciphers = self._ssl_context_ciphers(base_context)
            self.warnLog(self._ssl_context_summary(base_context, "default"))
            default_probe_msg, default_cipher = await self._probe_tls_details(
                base_context, "default"
            )
            self.warnLog(default_probe_msg)
            fallback_context = self._get_kasa_ssl_fallback_context()
            self.warnLog(self._ssl_context_summary(fallback_context, "unsecure"))
            fallback_probe_msg, fallback_cipher = await self._probe_tls_details(
                fallback_context, "unsecure"
            )
            self.warnLog(fallback_probe_msg)
            required_cipher = fallback_cipher or default_cipher
            if required_cipher and required_cipher not in default_ciphers:
                self.warnLog(
                    f"Please report this issue to maintainers of python-kasa at https://github.com/python-kasa/python-kasa/issues/new so that the required cipher {required_cipher} can be added. The cipher most likely needs to be added to /transports/sslaestransport.py."
                )
            else:
                self.warnLog(
                    f"Please report this issue to maintainers of pytapo at https://github.com/JurajNyiri/pytapo/issues/new since the required cipher {required_cipher} is inside of the default context but the request still failed."
                )
            self.warnLog(
                "Integration will continue to work and accept any cipher on the device, but will output this warning message."
            )
        except Exception:
            pass

    def _get_kasa_ssl_fallback_context(self):
        if self._kasa_ssl_fallback_context is None:
            self._kasa_ssl_fallback_context = self._create_kasa_unsecure_ssl_context()
        return self._kasa_ssl_fallback_context

    def _apply_kasa_ssl_fallback_to_transport(self):
        self.debugLog("_apply_kasa_ssl_fallback_to_transport called")
        transport = getattr(getattr(self.dev, "protocol", None), "_transport", None)
        if not transport:
            self.debugLog("Failed to apply ssl fallback, transport does not exist.")
            return False
        try:
            transport._ssl_context = self._get_kasa_ssl_fallback_context()
            self.debugLog("SSL context applied.")
            return True
        except Exception as err:
            self.warnLog(f"Failed to apply SSL context: {err}")
            return False

    async def _kasa_connect_without_update(self, config):
        from kasa.device_factory import get_protocol
        from kasa.smart import SmartDevice

        protocol = get_protocol(config=config, strict=True)
        if protocol is None:
            raise Exception(
                f"Unsupported device for {config.host}: "
                f"{config.connection_type.device_family.value}"
            )
        return SmartDevice(host=config.host, config=config, protocol=protocol)

    async def close(self):
        try:
            if self.dev and getattr(self.dev, "protocol", None):
                await self.dev.protocol.close()
        except Exception:
            pass
        self.dev = None

    def debugLog(self, msg: str):
        pass

    def warnLog(self, msg: str):
        pass

    def _ssl_context_ciphers(self, context):
        pass

    def _ssl_context_summary(self, context, label):
        pass

    def _format_verify_mode(self, mode):
        pass

    def _iter_exception_chain(self, err):
        pass

    def _format_tls_version(self, version):
        pass

    async def _probe_tls_details(self, context, label, timeout=3):
        pass
