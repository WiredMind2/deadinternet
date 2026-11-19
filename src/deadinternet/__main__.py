from pathlib import Path

import uvicorn

from deadinternet.api.app import create_app
from deadinternet.propose.agent import RepairProposer
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


if __name__ == "__main__":
    main()
