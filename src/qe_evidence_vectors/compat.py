from __future__ import annotations

import warnings

URLLIB3_LIBRESSL_WARNING_RE = r"urllib3 v2 only supports OpenSSL.*"


def silence_urllib3_libressl_warning() -> None:
    for action, message, category, _module, _line in warnings.filters:
        if (
            action == "ignore"
            and getattr(message, "pattern", None) == URLLIB3_LIBRESSL_WARNING_RE
            and category is Warning
        ):
            return
    warnings.filterwarnings(
        "ignore",
        message=URLLIB3_LIBRESSL_WARNING_RE,
    )
