"""Fuzz metric snapshots against an in-memory store."""
import sys
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "fuzz"))

from corpus import EXPECTED, text  # noqa: E402
from deadinternet.metrics.pull import record_snapshot  # noqa: E402
from deadinternet.store import Store  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    store = Store(":memory:")
    try:
        record_snapshot(
            store,
            text(fdp, 12),
            {
                "views": fdp.ConsumeIntInRange(0, 1_000_000),
                "watch_time_seconds": fdp.ConsumeIntInRange(0, 1_000_000),
                "likes": fdp.ConsumeIntInRange(0, 100_000),
                "comments": fdp.ConsumeIntInRange(0, 100_000),
                "shares": fdp.ConsumeIntInRange(0, 100_000),
                "failed": fdp.ConsumeBool(),
                "captured_at": "2026-01-01T00:00:00Z",
            },
        )
    except EXPECTED:
        return
    finally:
        store._conn.close()


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
