from __future__ import annotations


_TRUNCATION_ENABLED = True


def set_truncation_enabled(enabled: bool) -> None:
    global _TRUNCATION_ENABLED
    _TRUNCATION_ENABLED = bool(enabled)


def is_truncation_enabled() -> bool:
    return _TRUNCATION_ENABLED

def truncate(text: str, limit: int = 4000) -> str:
    if not _TRUNCATION_ENABLED:
        return text
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...[truncated {len(text) - limit} characters]"
