"""The lab's two entrypoints.

`python -m deadinternet` serves the admin API on 127.0.0.1:8000 — the
local dashboard's write surface, keep it off the internet. `python -m
deadinternet --public [port]` serves the click redirect on its own
process and port (US-034) — the one an operator exposes to the open
internet.
"""

import os
import sys
from pathlib import Path

import uvicorn

from deadinternet.api.app import create_app
from deadinternet.propose.agent import RepairProposer
from deadinternet.public_app import create_public_app
from deadinternet.runtime import LivePublisher, LiveRenderer
from deadinternet.store import Store


def _db_path() -> Path:
    """The lab database under the repo root, whatever the current directory is.

    The package lives at <repo>/src/deadinternet/__main__.py, so the repo
    root is three levels up from this file.
    """
    return Path(__file__).resolve().parents[2] / "data" / "deadinternet.sqlite"


def main() -> None:
    store = Store(str(_db_path()))
    app = create_app(
        store,
        renderer=LiveRenderer(),
        publisher=LivePublisher(),
        proposer=RepairProposer.from_env(),
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)


def main_public(port: int | None = None) -> None:
    """Serve the public click app (US-034) as its own process and port.

    This runs beside the admin app against the SAME repo-rooted lab
    database, in a separate process. SQLite handles that cross-process
    access with its default rollback-journal file locking — WAL is NOT
    enabled in this codebase (verified: store/db.py opens the file with
    default pragmas and no PRAGMA journal_mode exists anywhere in the
    package) — so a click this process commits is visible to the admin
    process immediately, and simultaneous writers queue on the file lock
    (sqlite's default 5s busy timeout) instead of corrupting. The host
    defaults to loopback like the admin app: expose this process through
    a reverse proxy, or set DEADINTERNET_PUBLIC_HOST when the box itself
    is the front door.
    """
    store = Store(str(_db_path()))
    app = create_public_app(store)
    if port is None:
        raw = os.environ.get("DEADINTERNET_PUBLIC_PORT", "")
        port = int(raw) if raw.strip() else 8001
    uvicorn.run(
        app,
        host=os.environ.get("DEADINTERNET_PUBLIC_HOST") or "127.0.0.1",
        port=port,
    )


def _dispatch(argv: list[str]) -> None:
    """--public [port] serves the click app; no flag serves the admin API."""
    if argv and argv[0] == "--public":
        main_public(port=int(argv[1]) if len(argv) > 1 else None)
    else:
        main()


if __name__ == "__main__":
    _dispatch(sys.argv[1:])
