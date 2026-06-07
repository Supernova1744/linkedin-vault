from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def validate_ollama_url(url: str) -> tuple[bool, str]:
    """Validate a user-supplied Ollama base URL.

    Returns (is_valid, warning_or_error_message).
    - is_valid=False means the URL must be rejected (dangerous scheme).
    - is_valid=True with a non-empty message means the URL is accepted but
      the message should be shown as a warning (non-localhost target).
    """
    if not url:
        return True, ""

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL could not be parsed."

    if parsed.scheme not in ("http", "https"):
        return False, f"Scheme '{parsed.scheme}' is not allowed — use http or https."

    host = parsed.hostname or ""
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = host in ("localhost",)

    if not is_loopback:
        return True, (
            f"Warning: Ollama URL '{host}' is not localhost — "
            "enrichment and chat will send your saved posts to that server."
        )

    return True, ""
