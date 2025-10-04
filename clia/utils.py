from __future__ import annotations


_TRUNCATION_ENABLED = True
_TRUNCATION_LIMIT = 4000


def set_truncation_enabled(enabled: bool) -> None:
    global _TRUNCATION_ENABLED
    _TRUNCATION_ENABLED = bool(enabled)


def is_truncation_enabled() -> bool:
    return _TRUNCATION_ENABLED


def set_truncation_limit(limit: int) -> None:
    global _TRUNCATION_LIMIT
    if limit > 0:
        _TRUNCATION_LIMIT = limit


def get_truncation_limit() -> int:
    return _TRUNCATION_LIMIT


def truncate(text: str, limit: int | None = None) -> str:
    if not _TRUNCATION_ENABLED:
        return text
    effective_limit = limit if limit is not None and limit > 0 else _TRUNCATION_LIMIT
    if len(text) <= effective_limit:
        return text
    return f"{text[:effective_limit]}\n...[truncated {len(text) - effective_limit} characters]"
