"""Utility helpers for serialization and hashing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def model_to_dict(value: Any) -> Any:
    """Convert pydantic models recursively into JSON-serializable dicts."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, list):
        return [model_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {k: model_to_dict(v) for k, v in value.items()}
    return value


def stable_hash(payload: Any) -> str:
    """Build a deterministic SHA256 hash for any JSON-serializable payload."""
    normalized = json.dumps(model_to_dict(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    """Return a UTC timestamp with explicit timezone info."""
    return datetime.now(timezone.utc).isoformat()
