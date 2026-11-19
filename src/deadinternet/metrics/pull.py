"""Record a platform metric snapshot. A failed pull writes nothing."""

from datetime import datetime, timezone


def record_snapshot(store, publication_id: str, metrics: dict) -> None:
    """Insert one snapshot. `failed=True` does not insert a zero row.

    A count the caller left absent (None) stays absent (US-038): "not
    measured" is never stored as a measured zero. An explicit 0 is a real
    measurement and is kept.
    """
    if metrics.get("failed") is True:
        return
    captured_at = metrics.get("captured_at") or _now()
    store.add_snapshot(
        publication_id,
        captured_at,
        _count(metrics.get("views")),
        _count(metrics.get("watch_time_seconds")),
        _count(metrics.get("likes")),
        _count(metrics.get("comments")),
        _count(metrics.get("shares")),
    )


def _count(value) -> int | None:
    return None if value is None else int(value)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
