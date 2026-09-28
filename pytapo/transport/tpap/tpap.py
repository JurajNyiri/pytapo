"""TPAP transport: the SPAKE2+ login and AES-128-CCM "/stok=<stok>/ds" channel
that recent Tapo camera firmware uses instead of the encrypt_type 3 login.

Cameras on this firmware answer the old login with error -40211. They advertise
it in `login/discover` as {"tpap": {"pake": [2], ...}}. Protocol write-up:
https://github.com/freeKC/tapo-v4-protocol
"""

import asyncio
import base64
import json
import os
import struct
import time

import requests
from Crypto.Cipher import AES

from ...const import CONNECTION_TIMEOUT, EncryptionMethod
from .spake2p import (
    Spake2pClient,
    apply_extra_crypt,
    md5_hex,
    sha256_hex_upper,
)

# The camera user is always the literal "admin", sent hashed the way the app does
# (libtapocameranetwork j2.u): sha256 upper hex if user_hash_type == 1, else md5 hex.
CAMERA_USER = "admin"
SESSION_ERRORS = (-40401, -40421)
# Keep using a session until it has really expired, as the app does
# (KasaTpapSessionCacheProvider): there is no benefit in renewing early.
RENEW_BEFORE_EXPIRY_SECONDS = 0
# A Tapo C200 (fw 1.4.6) refuses the first pake_share after a session ends
# with -40401 and accepts the same credential a few seconds later. Re-logins
# therefore retry the known-good passcode once instead of trying another one.
RELOGIN_RETRY_DELAY_SECONDS = 2


def _lockoutSeconds(response):
    """Seconds left on a login lockout, if the camera reported one."""
    for holder in (
        response.get("error_info"),
        response.get("data"),
        (response.get("result") or {}).get("data"),
    ):
        if isinstance(holder, dict) and int(holder.get("sec_left") or 0) > 0:
            return int(holder["sec_left"])
    return 0


class TpapError(Exception):
    def __init__(self, code, message=""):
        super().__init__(f"error_code={code} {message}".strip())
        self.code = code


def discover_tpap(host, controlPort=443, timeout=CONNECTION_TIMEOUT):
    """Return the camera's tpap info (dict) if it offers the TPAP password login."""
    try:
        res = requests.post(
            f"https://{host}:{controlPort}/",
            json={"method": "login", "params": {"sub_method": "discover"}},
            verify=False,
            timeout=timeout,
        ).json()
    except (requests.RequestException, ValueError):
        return None
    tpap = (res.get("result") or {}).get("tpap") if isinstance(res, dict) else None
    if isinstance(tpap, dict) and 2 in (tpap.get("pake") or []):
        return tpap
    return None


def rejects_legacy_login(host, controlPort=443, timeout=CONNECTION_TIMEOUT):
    """True if the camera answers the encrypt_type 3 login probe with -40211.

    Some TPAP cameras (e.g. C510W fw 1.3.4) refuse login/discover with -40209 and
    only advertise the new login over UDP discovery. They still answer the probe
    the old transport sends first with -40211. The probe carries no password, so
    it cannot count towards the camera's lockout.
    """
    try:
        res = requests.post(
            f"https://{host}:{controlPort}/",
            json={
                "method": "login",
                "params": {
                    "encrypt_type": "3",
                    "username": CAMERA_USER,
                    "cnonce": os.urandom(8).hex().upper(),
                },
            },
            verify=False,
            timeout=timeout,
        ).json()
    except (requests.RequestException, ValueError):
        return False
    return isinstance(res, dict) and res.get("error_code") == -40211


class Tpap:
    def __init__(
        self,
        host,
        controlPort,
        user,
        password,
        cloudPassword="",
        hass=None,
        asyncHandler=None,
    ):
        self.host = host
        self.controlPort = controlPort or 443
        # TPAP authenticates with the TP-Link cloud password, not the camera account.
        self.password = cloudPassword or password
        self.hass = hass
        self.asyncHandler = asyncHandler
        self.baseUrl = f"https://{host}:{self.controlPort}"
        self.session = requests.Session()
        self.session.verify = False
        self.tpapInfo = None
        self.stok = None
        self.seq = None
        self.key = None
        self.nonce = None
        self.expiresAt = 0.0
        # Which passcode worked last time, so a re-login does not spend a failed
        # attempt (they count towards the camera's lockout) on a known-bad one.
        self.passcodeIndex = None
        self._lock = None

    # -- transport interface --------------------------------------------------
    async def authenticate(self, retry=False):
        async with self._getLock():
            if not self._loggedIn():
                await self._runBlocking(self._login)
            return True

    async def send(self, request, retry=0):
        async with self._getLock():
            return await self._runBlocking(self._sendSync, request)

    def getEncryptionMethod(self):
        # Media port 8800 selects its actual password hashing method from its
        # own WWW-Authenticate challenge. SHA256 is the correct fallback for
        # currently known TPAP cameras and preserves the public API contract.
        return EncryptionMethod.SHA256

    async def close(self):
        self._dropSession()

    # -- helpers --------------------------------------------------------------
    def _getLock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _runBlocking(self, func, *args):
        hass = self.hass or (self.asyncHandler.hass if self.asyncHandler else None)
        if hass is None:
            return func(*args)
        return await hass.async_add_executor_job(func, *args)

    def _headers(self, contentType):
        return {
            "requestByApp": "true",
            "Referer": self.baseUrl,
            "User-Agent": "Tapo CameraClient Android",
            "Content-Type": contentType,
            "Accept": contentType,
        }

    def _postLogin(self, params):
        res = self.session.post(
            self.baseUrl + "/",
            data=json.dumps({"method": "login", "params": params}),
            headers=self._headers("application/json"),
            timeout=CONNECTION_TIMEOUT,
        )
        return res.json()

    def _loggedIn(self):
        return (
            self.stok is not None
            and time.time() < self.expiresAt - RENEW_BEFORE_EXPIRY_SECONDS
        )

    def _dropSession(self):
        self.stok = self.key = self.nonce = self.seq = None
        self.expiresAt = 0.0

    def _username(self):
        if (self.tpapInfo or {}).get("user_hash_type") == 1:
            return sha256_hex_upper(CAMERA_USER)
        return md5_hex(CAMERA_USER)

    def _passcodes(self):
        # Same candidates and order as the app (j2.s, pake 2), without the local
        # access token which only the TP-Link cloud can supply.
        return [md5_hex(self.password), sha256_hex_upper(self.password)]

    # -- login ----------------------------------------------------------------
    def _login(self):
        # Same wording as the other transports, so callers (e.g. the Home Assistant
        # config flow probe, which passes an empty password) can tell a bad login
        # apart from "not a Tapo device". An empty password never reaches the
        # camera: every failed attempt counts towards its lockout.
        if not self.password:
            raise Exception("Invalid authentication data")
        if self.tpapInfo is None:
            self.tpapInfo = discover_tpap(self.host, self.controlPort) or {}
        passcodes = self._passcodes()
        if self.passcodeIndex is not None:
            # Re-login: only the passcode that worked before (never spend a failed
            # attempt on a known-bad one), retried once for the refusal above.
            attempts = [self.passcodeIndex, self.passcodeIndex]
        else:
            attempts = list(range(len(passcodes)))  # first login: the app's order
        lastError = None
        for number, index in enumerate(attempts):
            if number and index == attempts[number - 1]:
                time.sleep(RELOGIN_RETRY_DELAY_SECONDS)
            try:
                self._loginWith(passcodes[index])
                self.passcodeIndex = index
                return
            except TpapError as err:
                lastError = err
                if err.code != -40401:  # only a refused passcode is worth a retry
                    raise
        raise Exception("Invalid authentication data") from lastError

    def _loginWith(self, passcode):
        userRandom = base64.b64encode(os.urandom(32)).decode()
        register = self._postLogin(
            {
                "sub_method": "pake_register",
                "username": self._username(),
                "user_random": userRandom,
                "cipher_suites": [1],
                "encryption": ["aes_128_ccm"],
                "passcode_type": "userpw",
            }
        )
        if "result" not in register:
            raise TpapError(register.get("error_code"), "pake_register failed")
        result = register["result"]
        credential = apply_extra_crypt(passcode, result.get("extra_crypt"))
        client = Spake2pClient(
            result, userRandom, credential, int.from_bytes(os.urandom(32), "big")
        )
        share = self._postLogin(
            {
                "sub_method": "pake_share",
                "user_share": base64.b64encode(client.Xb).decode(),
                "user_confirm": base64.b64encode(client.user_confirm).decode(),
            }
        )
        if "result" not in share:
            secondsLeft = _lockoutSeconds(share)
            if secondsLeft:
                raise Exception(
                    f"Temporary Suspension: Try again in {secondsLeft} seconds"
                )
            raise TpapError(share.get("error_code"), "pake_share failed")
        shareResult = share["result"]
        if not client.device_confirm_ok(base64.b64decode(shareResult["dev_confirm"])):
            raise TpapError(None, "device confirmation mismatch")
        self.key, self.nonce = client.session_key_and_nonce()
        self.stok = shareResult["stok"]
        self.seq = int(shareResult["start_seq"])
        self.expiresAt = time.time() + int(shareResult.get("expired") or 3600)

    # -- encrypted channel ----------------------------------------------------
    def _sendSync(self, request):
        # The /ds channel only takes multipleRequest; wrap single calls and hand
        # back the single response so callers see the same shape as before.
        single = request.get("method") != "multipleRequest"
        inner = (
            {"method": "multipleRequest", "params": {"requests": [request]}}
            if single
            else request
        )
        payload = json.dumps(inner, separators=(",", ":")).encode()
        for attempt in (0, 1):
            try:
                if not self._loggedIn():
                    self._login()
                response = self._roundTrip(payload)
                break
            except TpapError as err:
                self._dropSession()  # a refused request ends the session camera-side
                if attempt or err.code not in SESSION_ERRORS:
                    raise
            except requests.RequestException:
                self._dropSession()
                if attempt:
                    raise
        if single:
            responses = (response.get("result") or {}).get("responses") or []
            if responses:
                return responses[0]
        return response

    def _nonceFor(self, seq):
        return self.nonce[:8] + struct.pack(">I", seq & 0xFFFFFFFF)

    def _roundTrip(self, payload):
        seq = self.seq
        self.seq += 1
        cipher = AES.new(self.key, AES.MODE_CCM, nonce=self._nonceFor(seq), mac_len=16)
        body = (
            struct.pack(">I", seq & 0xFFFFFFFF)
            + cipher.encrypt(payload)
            + cipher.digest()
        )
        res = self.session.post(
            f"{self.baseUrl}/stok={self.stok}/ds",
            data=body,
            headers=self._headers("application/octet-stream"),
            timeout=CONNECTION_TIMEOUT,
        )
        raw = res.content
        if raw[:1] == b"{":  # refused before decryption, sent in plain JSON
            try:
                code = json.loads(raw).get("error_code")
            except ValueError:
                code = None
            raise TpapError(code, "request refused")
        if len(raw) < 20:
            raise TpapError(
                None, f"short reply ({len(raw)} bytes, HTTP {res.status_code})"
            )
        replySeq = struct.unpack(">I", raw[:4])[0]
        decipher = AES.new(
            self.key, AES.MODE_CCM, nonce=self._nonceFor(replySeq), mac_len=16
        )
        try:
            plain = decipher.decrypt_and_verify(raw[4:-16], raw[-16:])
        except ValueError as err:
            raise TpapError(None, f"reply failed authentication: {err}") from err
        return json.loads(plain)
