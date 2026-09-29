"""Per-request timeouts for the desktop run, and pushing them through provider wrappers.

Masaüstü koşusunda her isteğin zaman aşımını hesaplar ve sağlayıcı sarmalayıcılarının içindeki
gerçek sağlayıcıya uygular. Computes each request's timeout and applies it to the real provider.
"""

from __future__ import annotations

from layoutkeep.core import tunables

_FIRST_BATCH_BASE_TIMEOUT_S = 240.0
_WARM_BATCH_BASE_TIMEOUT_S = 15.0
_DEFAULT_CHARS_PER_SECOND = 12.0
_MIN_BATCH_TIMEOUT_S = 30.0
_MAX_BATCH_TIMEOUT_S = 900.0


def batch_timeout(chars: int, *, is_first: bool, chars_per_second: float | None) -> float:
    # The first batch pays for a cold model load, and how long that takes is a property of the
    # machine, not of this code - so it is a setting (`timeout.first_batch_s`), with the constant
    # as the fallback. It used to be a declared-but-unread switch: visible in the dialog, wired to
    # nothing.
    first = tunables.get("timeout.first_batch_s")
    base = float(first if is_first and first else _FIRST_BATCH_BASE_TIMEOUT_S if is_first else _WARM_BATCH_BASE_TIMEOUT_S)
    rate = chars_per_second or _DEFAULT_CHARS_PER_SECOND
    estimate = base + chars / rate
    return max(_MIN_BATCH_TIMEOUT_S, min(_MAX_BATCH_TIMEOUT_S, estimate))


def set_provider_timeout(provider, seconds: float) -> None:
    target = provider
    while (inner := getattr(target, "inner", None)) is not None:
        target = inner
    if hasattr(target, "timeout"):
        target.timeout = seconds


def compute_batch_timeout(
    provider, configured_timeout: float | None, chars: int, *, is_first: bool, chars_per_second: float | None
) -> float:
    """Compute per-batch timeout and push it through any provider wrappers."""
    if configured_timeout:
        timeout = configured_timeout
    else:
        timeout = batch_timeout(chars, is_first=is_first, chars_per_second=chars_per_second)
    set_provider_timeout(provider, timeout)
    return timeout
