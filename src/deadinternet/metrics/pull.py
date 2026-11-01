"""Record a platform metric snapshot. A failed pull writes nothing."""

from datetime import datetime, timezone


def record_snapshot(store, publication_id: str, metrics: dict) -> None:
    """Insert one snapshot. `failed=True` does not insert a zero row."""
    if metrics.get("failed") is True:
        return
    captured_at = metrics.get("captured_at") or _now()
    store.add_snapshot(
        publication_id,
        captured_at,
        int(metrics.get("views") or 0),
        int(metrics.get("watch_time_seconds") or 0),
        int(metrics.get("likes") or 0),
        int(metrics.get("comments") or 0),
        int(metrics.get("shares") or 0),
    )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
