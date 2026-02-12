import base64
import asyncio
import time
import requests
import json
import hashlib
import copy
from ...const import EncryptionMethod, MAX_LOGIN_RETRIES
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from .TlsAdapter import TlsAdapter
from ...media_stream._utils import generate_nonce
from ...asyncHandler import AsyncHandler
from .const import (
    RETRY_BACKOFF_SECONDS,
    TRANSIENT_REQUEST_RETRIES,
    RETRYABLE_ERROR_CODES,
    AUTH_ERROR_CODES,
)

# Todo: retry timeout errors?


class pyTapo:

    def __init__(
        self,
        host: str,
        controlPort: int,
        user: str,
        password: str,
        asyncHandler: AsyncHandler,
        retryStok=True,
        hass=None,
        cloudPassword="",
        reuseSession=True,
        redactConfidentialInformation=True,
    ):
        self.host = host
        self.controlPort = controlPort
        self.user = user
        self.password = password
        self.retryStok = retryStok
        self.hass = hass
        self.asyncHandler = asyncHandler
        self.passwordEncryptionMethod = None
        self.seq = None
        self.lsk = None
        self.cnonce = None
        self.ivb = None
        self.stok = False
        self.cloudPassword = cloudPassword
        self.reuseSession = reuseSession
        self.redactConfidentialInformation = redactConfidentialInformation

        self.headers = {
            "Host": self._getControlHost(),
            "Referer": "https://{host}".format(host=self._getControlHost()),
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "Tapo CameraClient Android",
            "Connection": "keep-alive",
            "requestByApp": "true",
            "Content-Type": "application/json; charset=UTF-8",
        }
        self.hashedPassword = hashlib.md5(password.encode("utf8")).hexdigest().upper()
        self.hashedSha256Password = (
            hashlib.sha256(password.encode("utf8")).hexdigest().upper()
        )
        self.hashedCloudPassword = (
            hashlib.md5(cloudPassword.encode("utf8")).hexdigest().upper()
        )
        self.session = False
        self.isSecureConnectionCached = None
        self._send_lock = None
        self._send_lock_loop = None
        self._send_lock_owner = None
        self._send_lock_depth = 0

    async def send(self, request, retry=0):
        self.debugLog(f"send called, retry: {retry}")
        self.debugLog("Request:")
        self.debugLog(request)
        await self._acquire_send_lock()
        try:
            await self.authenticate()
            authValid = True
            url = self._getHostURL()
            secure_connection = await self._isSecureConnectionAsync()

            fullRequest = request
            if self.seq is not None and secure_connection:
                fullRequest = {
                    "method": "securePassthrough",
                    "params": {
                        "request": base64.b64encode(
                            self._encryptRequest(json.dumps(request).encode("utf-8"))
                        ).decode("utf8")
                    },
                }
                self.headers["Seq"] = str(self.seq)
                try:
                    self.headers["Tapo_tag"] = self._getTag(fullRequest)
                except Exception as err:
                    if str(err) == "Failure detecting hashing algorithm.":
                        authValid = False
                        self.debugLog(
                            "Failure detecting hashing algorithm on getTag, reauthenticating."
                        )
                    else:
                        raise err
                if not authValid:
                    return await self._retry_or_return(
                        request, retry, "Auth invalid on getTag", None
                    )
                self.seq += 1

            try:
                res = await self._requestAsync(
                    "POST",
                    url,
                    data=json.dumps(fullRequest),
                    headers=self.headers,
                    verify=False,
                )
                responseData = res.json()
            except requests.RequestException as err:
                return await self._retry_on_exception(request, retry, err)
            except ValueError as err:
                return await self._retry_on_exception(request, retry, err)
            if (
                secure_connection
                and "result" in responseData
                and "response" in responseData["result"]
            ):
                encryptedResponse = responseData["result"]["response"]
                encryptedResponse = base64.b64decode(responseData["result"]["response"])
                try:
                    responseJSON = json.loads(self._decryptResponse(encryptedResponse))
                except Exception as err:
                    if (
                        str(err) == "Padding is incorrect."
                        or str(err) == "PKCS#7 padding is incorrect."
                    ):
                        self.debugLog(f"{str(err)} Reauthenticating.")
                        authValid = False
                        responseJSON = responseData
                    else:
                        raise err
            else:
                responseJSON = responseData

            if not authValid:
                return await self._retry_or_return(
                    request, retry, "Auth invalid during decrypt", responseJSON
                )
            if self._has_top_error_code(responseJSON, RETRYABLE_ERROR_CODES):
                return await self._retry_or_return(
                    request, retry, "Retryable error code detected", responseJSON
                )
            if self._has_top_error_code(responseJSON, AUTH_ERROR_CODES):
                self.debugLog("Authentication error code detected, clearing session.")
                await self._clearSession()

            self.debugLog(f"Raw response: {responseJSON}")

            return responseJSON
        finally:
            await self._release_send_lock()

    async def _requestAsync(self, method, url, **kwargs):
        return await self._run_blocking(self._request, method, url, **kwargs)

    async def _run_blocking(self, func, *args, **kwargs):
        if self.asyncHandler is None or self.asyncHandler.hass is None:
            return func(*args, **kwargs)
        return await self.asyncHandler.hass.async_add_executor_job(
            lambda: func(*args, **kwargs)
        )

    async def authenticate(self, retry=False):
        await self._acquire_send_lock()
        try:
            if not self.stok:
                await self._run_blocking(self._refreshStok)
            return True
        finally:
            await self._release_send_lock()

    def getEncryptionMethod(self):
        return self.passwordEncryptionMethod

    async def close(self):
        await self._clearSession()

    def _clearSessionSync(self):
        self.debugLog("Clearing session state...")
        if self.session not in (False, None):
            try:
                self.session.close()
            except Exception as err:
                self.debugLog(f"Failed to close session: {err}")
        self.session = False
        self.stok = False
        self.seq = None
        self.lsk = None
        self.ivb = None
        self.cnonce = None
        self.passwordEncryptionMethod = None
        self.isSecureConnectionCached = None
        self.headers.pop("Seq", None)
        self.headers.pop("Tapo_tag", None)

    async def _clearSession(self):
        self._clearSessionSync()

    def _normalize_error_code(self, error_code):
        try:
            return int(error_code)
        except Exception:
            return None

    def _ensure_send_lock(self):
        loop = asyncio.get_running_loop()
        if self._send_lock is None or self._send_lock_loop != loop:
            self._send_lock = asyncio.Lock()
            self._send_lock_loop = loop
            self._send_lock_owner = None
            self._send_lock_depth = 0
        return self._send_lock

    async def _acquire_send_lock(self):
        lock = self._ensure_send_lock()
        task = asyncio.current_task()
        if self._send_lock_owner == task or (
            task is None and self._send_lock_owner is None and self._send_lock_depth > 0
        ):
            self._send_lock_depth += 1
            return
        await lock.acquire()
        self._send_lock_owner = task
        self._send_lock_depth = 1

    async def _release_send_lock(self):
        task = asyncio.current_task()
        if not (
            self._send_lock_owner == task
            or (
                task is None
                and self._send_lock_owner is None
                and self._send_lock_depth > 0
            )
        ):
            return
        self._send_lock_depth -= 1
        if self._send_lock_depth <= 0:
            self._send_lock_owner = None
            if self._send_lock is not None:
                self._send_lock.release()

    def _has_top_error_code(self, response, error_codes):
        if not isinstance(response, dict):
            return False
        code = self._normalize_error_code(response.get("error_code"))
        return code in error_codes if code is not None else False

    async def _retry_or_return(self, request, retry, reason, response):
        if retry >= MAX_LOGIN_RETRIES:
            self.debugLog(
                f"{reason}, giving up after {retry}/{MAX_LOGIN_RETRIES} retries."
            )
            return response
        self.debugLog(f"Response: {response}")
        self.debugLog(
            f"{reason}, clearing session and retrying: {retry + 1}/{MAX_LOGIN_RETRIES}"
        )
        await self._clearSession()
        await asyncio.sleep(RETRY_BACKOFF_SECONDS)
        return await self.send(request, retry + 1)

    async def _retry_on_exception(self, request, retry, err):
        if retry >= MAX_LOGIN_RETRIES:
            raise err
        self.debugLog(
            f"Request failed ({err}), clearing session and retrying: {retry + 1}/{MAX_LOGIN_RETRIES}"
        )
        await self._clearSession()
        await asyncio.sleep(RETRY_BACKOFF_SECONDS)
        return await self.send(request, retry + 1)

    def _encryptRequest(self, request):
        cipher = AES.new(self.lsk, AES.MODE_CBC, self.ivb)
        ct_bytes = cipher.encrypt(pad(request, AES.block_size))
        return ct_bytes

    def _decryptResponse(self, response):
        cipher = AES.new(self.lsk, AES.MODE_CBC, self.ivb)
        pt = cipher.decrypt(response)
        return unpad(pt, AES.block_size)

    def _getTag(self, request):
        tag = (
            hashlib.sha256(
                self._getHashedPassword().encode("utf8") + self.cnonce.encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        tag = (
            hashlib.sha256(
                tag.encode("utf8")
                + json.dumps(request).encode("utf8")
                + str(self.seq).encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        return tag

    def _isTransientConnectionReset(self, err):
        if not isinstance(err, requests.RequestException):
            return False
        err_str = str(err).lower()
        transient_markers = (
            "connection reset by peer",
            "remote end closed connection without response",
            "connection aborted",
            "remotedisconnected",
        )
        return any(marker in err_str for marker in transient_markers)

    def _resetHttpSession(self):
        if self.reuseSession and self.session not in (False, None):
            try:
                self.session.close()
            except Exception as err:
                self.debugLog(f"Failed to close session during reset: {err}")
            self.session = False

    def _request(self, method, url, transientRetryCount=0, **kwargs):
        if self.session is False and self.reuseSession is True:
            self.session = requests.session()
            self.session.mount("https://", TlsAdapter())

        if self.reuseSession is True:
            session = self.session
        else:
            session = requests.session()
            session.mount("https://", TlsAdapter())

        # Redaction of confidential data for logging purposes
        redactedKwargs = copy.deepcopy(kwargs)
        if self.redactConfidentialInformation:
            if "data" in redactedKwargs:
                redactedKwargsData = json.loads(redactedKwargs["data"])
                if "params" in redactedKwargsData:
                    if (
                        "password" in redactedKwargsData["params"]
                        and redactedKwargsData["params"]["password"] != ""
                    ):
                        redactedKwargsData["params"]["password"] = "REDACTED"
                    if (
                        "digest_passwd" in redactedKwargsData["params"]
                        and redactedKwargsData["params"]["digest_passwd"] != ""
                    ):
                        redactedKwargsData["params"]["digest_passwd"] = "REDACTED"
                    if (
                        "cnonce" in redactedKwargsData["params"]
                        and redactedKwargsData["params"]["cnonce"] != ""
                    ):
                        redactedKwargsData["params"]["cnonce"] = "REDACTED"
                redactedKwargs["data"] = redactedKwargsData
            if "headers" in redactedKwargs:
                redactedKwargsHeaders = redactedKwargs["headers"]
                if (
                    "Tapo_tag" in redactedKwargsHeaders
                    and redactedKwargsHeaders["Tapo_tag"] != ""
                ):
                    redactedKwargsHeaders["Tapo_tag"] = "REDACTED"
                if (
                    "Host" in redactedKwargsHeaders
                    and redactedKwargsHeaders["Host"] != ""
                ):
                    redactedKwargsHeaders["Host"] = "REDACTED"
                if (
                    "Referer" in redactedKwargsHeaders
                    and redactedKwargsHeaders["Referer"] != ""
                ):
                    redactedKwargsHeaders["Referer"] = "REDACTED"
                redactedKwargs["headers"] = redactedKwargsHeaders
        self.debugLog("New request:")
        self.debugLog(redactedKwargs)
        try:
            response = session.request(method, url, **kwargs)
        except requests.RequestException as err:
            if self.reuseSession is False:
                session.close()
            if (
                transientRetryCount < TRANSIENT_REQUEST_RETRIES
                and self._isTransientConnectionReset(err)
            ):
                transientRetryCount += 1
                self.debugLog(
                    f"Transient connection error ({err}), retrying request: {transientRetryCount}/{TRANSIENT_REQUEST_RETRIES}."
                )
                self._resetHttpSession()
                time.sleep(RETRY_BACKOFF_SECONDS)
                return self._request(
                    method,
                    url,
                    transientRetryCount=transientRetryCount,
                    **kwargs,
                )
            raise
        self.debugLog(f"Response status code: {response.status_code}")
        try:
            loadJson = json.loads(response.text)
            if self.redactConfidentialInformation:
                if "result" in loadJson:
                    if (
                        "stok" in loadJson["result"]
                        and loadJson["result"]["stok"] != ""
                    ):
                        loadJson["result"]["stok"] = "REDACTED"
                    if "data" in loadJson["result"]:
                        if (
                            "key" in loadJson["result"]["data"]
                            and loadJson["result"]["data"]["key"] != ""
                        ):
                            loadJson["result"]["data"]["key"] = "REDACTED"
                        if (
                            "nonce" in loadJson["result"]["data"]
                            and loadJson["result"]["data"]["nonce"] != ""
                        ):
                            loadJson["result"]["data"]["nonce"] = "REDACTED"
                        if (
                            "device_confirm" in loadJson["result"]["data"]
                            and loadJson["result"]["data"]["device_confirm"] != ""
                        ):
                            loadJson["result"]["data"]["device_confirm"] = "REDACTED"
            self.debugLog("Response:")
            self.debugLog(loadJson)
        except Exception as err:
            self.debugLog("Failed to load json:" + str(err))

        if self.reuseSession is False:
            response.close()
            session.close()
        return response

    async def _isSecureConnectionAsync(self):
        if self.isSecureConnectionCached is not None:
            return self.isSecureConnectionCached
        return await self._run_blocking(self._isSecureConnection)

    def _isSecureConnection(self):
        self.debugLog("_isSecureConnection called")
        if self.isSecureConnectionCached is None:
            self.debugLog("secure connection is not cached")
            url = "https://{host}".format(host=self._getControlHost())
            probe_cnonce = generate_nonce(8).decode().upper()
            data = {
                "method": "login",
                "params": {
                    "encrypt_type": "3",
                    "username": self.user,
                    "cnonce": probe_cnonce,
                },
            }
            self.debugLog("Checking for secure connection...")
            res = self._request(
                "POST", url, data=json.dumps(data), headers=self.headers, verify=False
            )
            response = res.json()
            self.isSecureConnectionCached = (
                "error_code" in response
                and response["error_code"] == -40413
                and "result" in response
                and "data" in response["result"]
                and "encrypt_type" in response["result"]["data"]
                and "3" in response["result"]["data"]["encrypt_type"]
            )
        return self.isSecureConnectionCached

    def _validateDeviceConfirm(self, nonce, deviceConfirm):
        self.passwordEncryptionMethod = None
        hashedNoncesWithSHA256 = (
            hashlib.sha256(
                self.cnonce.encode("utf8")
                + self.hashedSha256Password.encode("utf8")
                + nonce.encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        hashedNoncesWithMD5 = (
            hashlib.sha256(
                self.cnonce.encode("utf8")
                + self.hashedPassword.encode("utf8")
                + nonce.encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        if deviceConfirm == (hashedNoncesWithSHA256 + nonce + self.cnonce):
            self.passwordEncryptionMethod = EncryptionMethod.SHA256
        elif deviceConfirm == (hashedNoncesWithMD5 + nonce + self.cnonce):
            self.passwordEncryptionMethod = EncryptionMethod.MD5
        return self.passwordEncryptionMethod is not None

    def _getHashedPassword(self):
        if self.passwordEncryptionMethod == EncryptionMethod.MD5:
            return self.hashedPassword
        elif self.passwordEncryptionMethod == EncryptionMethod.SHA256:
            return self.hashedSha256Password
        else:
            raise Exception("Failure detecting hashing algorithm.")

    def _generateEncryptionToken(self, tokenType, nonce):
        hashedKey = (
            hashlib.sha256(
                self.cnonce.encode("utf8")
                + self._getHashedPassword().encode("utf8")
                + nonce.encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        return hashlib.sha256(
            (
                tokenType.encode("utf8")
                + self.cnonce.encode("utf8")
                + nonce.encode("utf8")
                + hashedKey.encode("utf8")
            )
        ).digest()[:16]

    def _responseIsOK(self, res, data=None):
        if res is not None and (
            (res.status_code != 200 and not self._isSecureConnection())
            or (
                res.status_code != 200
                and res.status_code != 500
                and self._isSecureConnection()  # pass responseIsOK for secure connections 500 which are communicating expiring session
            )
        ):
            raise Exception(
                "Error communicating with Tapo Camera. Status code: "
                + str(res.status_code)
            )
        try:
            if data is None:
                data = res.json()
            if "error_code" not in data or data["error_code"] == 0:
                return True
            return False
        except Exception as e:
            raise Exception("Unexpected response from Tapo Camera: " + str(e))

    def _refreshStok(self, loginRetryCount=0):
        self.debugLog("Refreshing stok...")
        try:
            self.cnonce = generate_nonce(8).decode().upper()
            url = "https://{host}".format(host=self._getControlHost())
            if self._isSecureConnection():
                self.debugLog("Connection is secure.")
                data = {
                    "method": "login",
                    "params": {
                        "cnonce": self.cnonce,
                        "encrypt_type": "3",
                        "username": self.user,
                    },
                }
            else:
                self.debugLog("Connection is insecure.")
                data = {
                    "method": "login",
                    "params": {
                        "hashed": True,
                        "password": self.hashedPassword,
                        "username": self.user,
                    },
                }
            res = self._request(
                "POST", url, data=json.dumps(data), headers=self.headers, verify=False
            )
            self.debugLog("Status code: " + str(res.status_code))
        except (requests.RequestException, ValueError) as err:
            if loginRetryCount < MAX_LOGIN_RETRIES:
                loginRetryCount += 1
                self.debugLog(
                    f"Request failed ({err}), retrying: {loginRetryCount}/{MAX_LOGIN_RETRIES}."
                )
                self._clearSessionSync()
                time.sleep(RETRY_BACKOFF_SECONDS)
                return self._refreshStok(loginRetryCount)
            raise err

        if res.status_code == 401:
            try:
                data = res.json()
                if data["result"]["data"]["code"] == -40411:
                    self.debugLog("Code is -40411, raising Exception.")
                    raise Exception("Invalid authentication data")
            except Exception as e:
                if str(e) == "Invalid authentication data":
                    raise e
                else:
                    pass

        try:
            responseData = res.json()
        except ValueError as err:
            if loginRetryCount < MAX_LOGIN_RETRIES:
                loginRetryCount += 1
                self.debugLog(
                    f"Invalid JSON response ({err}), retrying: {loginRetryCount}/{MAX_LOGIN_RETRIES}."
                )
                self._clearSessionSync()
                time.sleep(RETRY_BACKOFF_SECONDS)
                return self._refreshStok(loginRetryCount)
            raise err
        if self._isSecureConnection():
            self.debugLog("Processing secure response.")
            if (
                "result" in responseData
                and "data" in responseData["result"]
                and "nonce" in responseData["result"]["data"]
                and "device_confirm" in responseData["result"]["data"]
            ):
                self.debugLog("Validating device confirm.")
                nonce = responseData["result"]["data"]["nonce"]
                if self._validateDeviceConfirm(
                    nonce, responseData["result"]["data"]["device_confirm"]
                ):  # sets self.passwordEncryptionMethod, password verified on client, now request stok
                    self.debugLog("Signing in with digestPasswd.")
                    digestPasswd = (
                        hashlib.sha256(
                            self._getHashedPassword().encode("utf8")
                            + self.cnonce.encode("utf8")
                            + nonce.encode("utf8")
                        )
                        .hexdigest()
                        .upper()
                    )
                    data = {
                        "method": "login",
                        "params": {
                            "cnonce": self.cnonce,
                            "encrypt_type": "3",
                            "digest_passwd": (
                                digestPasswd.encode("utf8")
                                + self.cnonce.encode("utf8")
                                + nonce.encode("utf8")
                            ).decode(),
                            "username": self.user,
                        },
                    }
                    try:
                        res = self._request(
                            "POST",
                            url,
                            data=json.dumps(data),
                            headers=self.headers,
                            verify=False,
                        )
                        responseData = res.json()
                    except (requests.RequestException, ValueError) as err:
                        if loginRetryCount < MAX_LOGIN_RETRIES:
                            loginRetryCount += 1
                            self.debugLog(
                                f"Request failed ({err}), retrying: {loginRetryCount}/{MAX_LOGIN_RETRIES}."
                            )
                            self._clearSessionSync()
                            time.sleep(RETRY_BACKOFF_SECONDS)
                            return self._refreshStok(loginRetryCount)
                        raise err
                    if (
                        "result" in responseData
                        and "start_seq" in responseData["result"]
                    ):
                        if (
                            "user_group" in responseData["result"]
                            and responseData["result"]["user_group"] != "root"
                        ):
                            self.debugLog(
                                "Incorrect user_group detected, raising Exception."
                            )
                            # encrypted control via 3rd party account does not seem to be supported
                            # see https://github.com/JurajNyiri/HomeAssistant-Tapo-Control/issues/456
                            raise Exception("Invalid authentication data")
                        self.debugLog("Generating encryption tokens.")
                        self.lsk = self._generateEncryptionToken("lsk", nonce)
                        self.ivb = self._generateEncryptionToken("ivb", nonce)
                        self.seq = responseData["result"]["start_seq"]
                else:
                    if (
                        self.retryStok
                        and (
                            "error_code" in responseData
                            and responseData["error_code"] == -40413
                        )
                        and loginRetryCount < MAX_LOGIN_RETRIES
                    ):
                        loginRetryCount += 1
                        self.debugLog(
                            f"Incorrect device_confirm value, retrying: {loginRetryCount}/{MAX_LOGIN_RETRIES}."
                        )
                        return self._refreshStok(loginRetryCount)
                    else:
                        self.debugLog(
                            "Incorrect device_confirm value, raising Exception."
                        )
                        raise Exception("Invalid authentication data")
        else:
            self.passwordEncryptionMethod = EncryptionMethod.MD5
        if (
            "result" in responseData
            and "data" in responseData["result"]
            and "time" in responseData["result"]["data"]
            and "max_time" in responseData["result"]["data"]
            and "sec_left" in responseData["result"]["data"]
            and responseData["result"]["data"]["sec_left"] > 0
        ):
            raise Exception(
                f"Temporary Suspension: Try again in {str(responseData['result']['data']['sec_left'])} seconds"
            )
        if (
            "data" in responseData
            and "code" in responseData["data"]
            and "sec_left" in responseData["data"]
            and responseData["data"]["code"] == -40404
            and responseData["data"]["sec_left"] > 0
        ):
            raise Exception(
                f"Temporary Suspension: Try again in {str(responseData['data']['sec_left'])} seconds"
            )

        if self._responseIsOK(res):
            self.debugLog("Saving stok.")
            self.stok = res.json()["result"]["stok"]
            return self.stok
        error_code = (
            responseData.get("error_code") if isinstance(responseData, dict) else None
        )
        if self.retryStok and loginRetryCount < MAX_LOGIN_RETRIES:
            if error_code in RETRYABLE_ERROR_CODES or (
                error_code is not None
                and error_code not in AUTH_ERROR_CODES
                and error_code != -40411
            ):
                loginRetryCount += 1
                self.debugLog(
                    f"Unexpected response ({error_code}), retrying: {loginRetryCount}/{MAX_LOGIN_RETRIES}."
                )
                self._clearSessionSync()
                time.sleep(RETRY_BACKOFF_SECONDS)
                return self._refreshStok(loginRetryCount)
        self.debugLog(
            f"Unexpected response ({error_code}), raising Exception: {responseData}"
        )
        raise Exception("Invalid authentication data")

    def _getHostURL(self):
        return "https://{host}/stok={stok}/ds".format(
            host=self._getControlHost(), stok=self.stok
        )

    def _getControlHost(self):
        return f"{self.host}:{self.controlPort}"

    def debugLog(self, msg: str):
        pass

    def warnLog(self, msg: str):
        pass
