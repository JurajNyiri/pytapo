import ssl
import asyncio
import hashlib
from .kasa.kasa import Kasa
from .const import TRANSPORT_METHODS
from ..logger import Logger
from contextlib import suppress


class Transport(Kasa):
    def __init__(
        self,
        host: str,
        controlPort: int,
        user: str,
        password: str,
        logger: Logger,
        method="kasa",
    ):
        if method not in TRANSPORT_METHODS:
            raise Exception(f"Incorrect transport method: {method}.")
        self.logger = logger
        self.method = method
        self.host = host
        self.controlPort = controlPort

        # todo change this so that Kasa is kept in self context and all the functions below use it automatically
        if self.method == "kasa":
            self.transport = Kasa
            self.transport.__init__(self, host, controlPort, user, password)

    async def authenticate(self, retry=False):
        return await self.transport.authenticate(self, retry)

    async def send(self, request, retry=0):
        return await self.transport.send(self, request, retry)

    def debugLog(self, msg):
        self.logger.debugLog(msg)

    def warnLog(self, msg):
        self.logger.warnLog(msg)

    def getEncryptionMethod(self):
        self.transport.getEncryptionMethod(self)

    async def close(self):
        await self.transport.close(self)

    def _ssl_context_ciphers(self, context):
        if context is None:
            return []
        ciphers = []
        with suppress(Exception):
            ciphers = [
                cipher.get("name")
                for cipher in context.get_ciphers()
                if cipher.get("name")
            ]
        return ciphers

    def _ssl_context_summary(self, context, label):
        if context is None:
            return f"{label} ssl context: <none>"
        ciphers = self._ssl_context_ciphers(context)
        min_version = self._format_tls_version(
            getattr(context, "minimum_version", None)
        )
        max_version = self._format_tls_version(
            getattr(context, "maximum_version", None)
        )
        return (
            f"{label} ssl context: openssl={ssl.OPENSSL_VERSION}, "
            f"tls_min={min_version}, tls_max={max_version}, "
            f"check_hostname={getattr(context, 'check_hostname', None)}, "
            f"verify_mode={self._format_verify_mode(getattr(context, 'verify_mode', None))}, "
            f"cipher_count={len(ciphers)}, ciphers={ciphers}"
        )

    def _format_verify_mode(self, mode):
        if mode == ssl.CERT_NONE:
            return "CERT_NONE"
        if mode == ssl.CERT_OPTIONAL:
            return "CERT_OPTIONAL"
        if mode == ssl.CERT_REQUIRED:
            return "CERT_REQUIRED"
        return str(mode)

    def _iter_exception_chain(self, err):
        seen = set()
        while err is not None and id(err) not in seen:
            yield err
            seen.add(id(err))
            err = getattr(err, "__cause__", None) or getattr(err, "__context__", None)

    def _format_tls_version(self, version):
        if version is None:
            return "unknown"
        tls_version_type = getattr(ssl, "TLSVersion", None)
        if tls_version_type and isinstance(version, tls_version_type):
            return version.name
        return str(version)

    async def _probe_tls_details(self, context, label, timeout=3):
        if context is None:
            return (f"Device TLS probe via {label}: context=<none>", None)
        writer = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self.host,
                    self.controlPort,
                    ssl=context,
                ),
                timeout=timeout,
            )
            ssl_obj = writer.get_extra_info("ssl_object") if writer else None
            cipher = ssl_obj.cipher() if ssl_obj else None
            cipher_name = cipher[0] if cipher else None
            tls_version = ssl_obj.version() if ssl_obj else None
            alpn = ssl_obj.selected_alpn_protocol() if ssl_obj else None
            cert = ssl_obj.getpeercert() if ssl_obj else None
            cert_subject = cert.get("subject") if cert else None
            cert_issuer = cert.get("issuer") if cert else None
            cert_not_before = cert.get("notBefore") if cert else None
            cert_not_after = cert.get("notAfter") if cert else None
            der = ssl_obj.getpeercert(binary_form=True) if ssl_obj else None
            cert_fingerprint = hashlib.sha256(der).hexdigest() if der else None
            return (
                f"Device TLS probe via {label}: tls_version={tls_version}, "
                f"cipher={cipher}, alpn={alpn}, "
                f"cert_subject={cert_subject}, cert_issuer={cert_issuer}, "
                f"cert_not_before={cert_not_before}, cert_not_after={cert_not_after}, "
                f"cert_sha256={cert_fingerprint}"
            ), cipher_name
        except Exception as err:
            return (f"Device TLS probe via {label} failed: {err}", None)
        finally:
            if writer is not None:
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
