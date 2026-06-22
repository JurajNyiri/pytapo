import ssl
from contextlib import suppress

from requests.adapters import HTTPAdapter
import urllib3
from urllib3.util import ssl_
from urllib3.poolmanager import PoolManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TlsAdapter(HTTPAdapter):
    def __init__(self, ssl_options=0, **kwargs):
        self.ssl_options = ssl_options
        super(TlsAdapter, self).__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, **pool_kwargs):
        options = self.ssl_options
        with suppress(AttributeError):
            # OP_IGNORE_UNEXPECTED_EOF added in Python 3.12; Tapo cameras do not
            # properly close TLS connections which raises SSLEOFError on newer Python.
            options |= ssl.OP_IGNORE_UNEXPECTED_EOF

        ctx = ssl_.create_urllib3_context(
            cert_reqs=ssl.CERT_NONE, options=options
        )

        ctx.set_ciphers("ALL:@SECLEVEL=0")

        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, ssl_context=ctx, **pool_kwargs
        )
