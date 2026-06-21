"""Windows OpenSSL / TLS setup for HTTPS requests.

Import this module before ``requests`` or other SSL-using libraries. On Windows
it removes Avast-style SSLKEYLOGFILE hooks, initializes Python's OpenSSL
applink, and wires certificate verification to the OS trust store via
``truststore``.
"""

from __future__ import annotations

import os
import sys


def apply_ssl_patch() -> None:
    if sys.platform != "win32":
        return

    # Remove SSLKEYLOGFILE if set (typically by Avast antivirus).
    # This variable points to an antivirus proxy and breaks OpenSSL initialization.
    if "SSLKEYLOGFILE" in os.environ:
        del os.environ["SSLKEYLOGFILE"]

    # Force Python's OpenSSL to initialize first by importing ssl and accessing
    # OPENSSL_VERSION. This establishes the applink before C++ bindings load.
    import ssl
    import _ssl

    _ = _ssl.OPENSSL_VERSION
    _ = ssl.OPENSSL_VERSION

    # Let requests/urllib3 verify certificates against the Windows certificate
    # store. This keeps Avast/corporate TLS inspection roots trusted without
    # disabling certificate verification.
    import truststore

    truststore.inject_into_ssl()


apply_ssl_patch()
