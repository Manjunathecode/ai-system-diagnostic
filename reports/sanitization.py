"""Defensive export sanitization; reports never carry credentials or raw secrets."""
from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


_SECRET_KEYS = ("api_key", "apikey", "password", "passwd", "token", "secret", "authorization", "cookie")
_PRIVATE_KEYS = ("user_name", "username", "computer_name", "pnpdeviceid", "instanceid", "document",
                 "temp_directory", "macaddress", "ipaddress", "ipv4address", "dnsserver",
                 "defaultipgateway", "cleanup_directory", "approved_directory")
_SECRET_TEXT = re.compile(r"(?i)(api[_-]?key|password|token|secret)\s*[:=]\s*[^\s,;]+")


def sanitize(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in _SECRET_KEYS + _PRIVATE_KEYS):
        return "[REDACTED]"
    if is_dataclass(value):
        return sanitize(asdict(value), key)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return "[LOCAL PATH REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): sanitize(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize(item, key) for item in value]
    if isinstance(value, str):
        return _SECRET_TEXT.sub(lambda match: match.group(1) + "=[REDACTED]", value)
    return value
