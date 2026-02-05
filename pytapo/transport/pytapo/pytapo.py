import base64
import requests
import json
import hashlib
import copy
from ...const import EncryptionMethod, MAX_LOGIN_RETRIES
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from .TlsAdapter import TlsAdapter
from ...media_stream._utils import generate_nonce

# todo: add method to start fresh
# todo: use the method to start fresh on various error codes, -40401 and others


class pyTapo:
    MULTI_REQUEST_BATCH_SIZE = 5

    def __init__(
        self,
        host: str,
        controlPort: int,
        user: str,
        password: str,
        retryStok=True,
        hass=None,
        cloudPassword="",
        reuseSession=False,
        redactConfidentialInformation=True,
    ):
        self.host = host
        self.controlPort = controlPort
        self.user = user
        self.password = password
        self.retryStok = retryStok
        self.hass = hass
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
            "Connection": "close",
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

    def _get_multi_request_entries(self, request):
        if not isinstance(request, dict):
            return None
        if request.get("method") != "multipleRequest":
            return None
        params = request.get("params")
        if not isinstance(params, dict):
            return None
        requests = params.get("requests")
        if not isinstance(requests, list):
            return None
        return requests

    async def _send_multi_request_in_batches(self, request, requests, retry):
        self.debugLog(
            f"Splitting multipleRequest into batches of {self.MULTI_REQUEST_BATCH_SIZE}"
        )
        combined_response = None
        step = self.MULTI_REQUEST_BATCH_SIZE
        total_requests = len(requests)
        total_batches = (total_requests + step - 1) // step
        for i in range(0, len(requests), step):
            batch_requests = requests[i : i + step]
            batch_num = (i // step) + 1
            self.debugLog(
                f"Sending multipleRequest batch {batch_num}/{total_batches} with {len(batch_requests)} requests"
            )
            batch_request = dict(request)
            batch_params = dict(request.get("params") or {})
            batch_params["requests"] = batch_requests
            batch_request["params"] = batch_params

            response = await self.send(batch_request, retry)
            if not self._responseIsOK(None, response):
                self.debugLog(
                    f"multipleRequest batch {batch_num}/{total_batches} returned error response, aborting"
                )
                return response

            if combined_response is None:
                combined_response = response
                if isinstance(combined_response.get("result"), dict):
                    combined_response["result"]["responses"] = []
                else:
                    combined_response["result"] = {"responses": []}
                self.debugLog("Initialized combined multipleRequest response")

            responses = response.get("result", {}).get("responses")
            if not isinstance(responses, list):
                self.debugLog(
                    f"multipleRequest batch {batch_num}/{total_batches} missing responses list, aborting"
                )
                return response
            self.debugLog(
                f"Appending {len(responses)} responses from batch {batch_num}/{total_batches}"
            )
            combined_response["result"]["responses"].extend(responses)

        if combined_response is not None:
            total_responses = len(
                combined_response.get("result", {}).get("responses", [])
            )
            self.debugLog(
                f"Combined multipleRequest response has {total_responses} responses"
            )
        return combined_response

    async def send(self, request, retry=0):
        self.debugLog(f"send called, retry: {retry}")
        self.debugLog("Request:")
        self.debugLog(request)
        await self.authenticate()
        multi_requests = self._get_multi_request_entries(request)
        if (
            multi_requests is not None
            and len(multi_requests) > self.MULTI_REQUEST_BATCH_SIZE
        ):
            return await self._send_multi_request_in_batches(
                request, multi_requests, retry
            )
        authValid = True
        url = self._getHostURL()

        if self.seq is not None and self._isSecureConnection():
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
            self.seq += 1

        res = self._request(
            "POST",
            url,
            data=json.dumps(fullRequest),
            headers=self.headers,
            verify=False,
        )
        responseData = res.json()
        if (
            self._isSecureConnection()
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
                    authValid = False  # todo handle this properly
                else:
                    raise err
        else:
            responseJSON = res.json()

        self.debugLog(f"Raw response: {responseJSON}")

        return responseJSON

    async def authenticate(self, retry=False):
        if not self.stok:
            if self.hass is None:
                return self._refreshStok()
            else:
                await self.hass.async_add_executor_job(self._refreshStok)
        return True

    def getEncryptionMethod(self):
        return self.passwordEncryptionMethod

    # not needed
    async def close(self):
        pass

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

    def _request(self, method, url, **kwargs):
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
        response = session.request(method, url, **kwargs)
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

        responseData = res.json()
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
                    res = self._request(
                        "POST",
                        url,
                        data=json.dumps(data),
                        headers=self.headers,
                        verify=False,
                    )
                    responseData = res.json()
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
        if (
            self.retryStok
            and ("error_code" in responseData and responseData["error_code"] == -40413)
            and loginRetryCount < MAX_LOGIN_RETRIES
        ):
            loginRetryCount += 1
            self.debugLog(
                f"Unexpected response, retrying: {loginRetryCount}/{MAX_LOGIN_RETRIES}."
            )
            return self._refreshStok(loginRetryCount)
        else:
            self.debugLog("Unexpected response, raising Exception.")
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
