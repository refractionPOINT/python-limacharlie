"""Fast JSON serialization/deserialization with orjson fallback.

Provides a unified API for JSON operations that uses orjson when available
(~3-10x faster than stdlib json) and falls back to stdlib json otherwise.

orjson is a mandatory dependency (specified in pyproject.toml) but the
fallback ensures the package still works if orjson cannot be installed
on a particular platform (e.g. missing Rust compiler for source builds).

Usage:
    from limacharlie.json_compat import dumps, loads, dumps_pretty

    # Compact JSON (no extra whitespace)
    s = dumps({"key": "value"})

    # Pretty-printed JSON (2-space indent)
    s = dumps_pretty({"key": "value"})

    # Parse JSON (str or bytes)
    obj = loads('{"key": "value"}')
"""

from __future__ import annotations

import json
from typing import Any

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    orjson = None  # type: ignore[assignment]
    HAS_ORJSON = False


def dumps(data: Any) -> str:
    """Serialize to compact JSON string (no extra whitespace).

    Uses orjson when available for ~5-10x faster serialization.

    Args:
        data: Any JSON-serializable Python object.

    Returns:
        Compact JSON string.
    """
    if orjson is not None:
        return orjson.dumps(data, option=orjson.OPT_NON_STR_KEYS).decode("utf-8")
    return json.dumps(data, default=str, separators=(",", ":"))


def dumps_pretty(data: Any) -> str:
    """Serialize to pretty-printed JSON (2-space indent).

    Uses orjson when available for ~5-10x faster serialization.

    Args:
        data: Any JSON-serializable Python object.

    Returns:
        Pretty-printed JSON string.
    """
    if orjson is not None:
        return orjson.dumps(
            data,
            option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS,
        ).decode("utf-8")
    return json.dumps(data, indent=2, default=str)


def loads(data: bytes | str) -> Any:
    """Parse JSON from string or bytes.

    Uses orjson when available for ~3-6x faster deserialization.

    Args:
        data: JSON string or bytes.

    Returns:
        Parsed Python object.
    """
    if orjson is not None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return orjson.loads(data)
    return json.loads(data)


def backend_name() -> str:
    """Return the name of the active JSON backend for debug logging."""
    return "orjson" if HAS_ORJSON else "stdlib json"
