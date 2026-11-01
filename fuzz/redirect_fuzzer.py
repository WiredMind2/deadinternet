"""Fuzz the click redirect against a real store."""
import sys
from dataclasses import replace
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "fuzz"))

from corpus import EXPECTED, experiment_from, text  # noqa: E402
from deadinternet.domain.experiment import Affiliate  # noqa: E402
from deadinternet.store import Store  # noqa: E402
from deadinternet.track.redirect import hit  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    code = text(fdp, 12)
    row = replace(experiment_from(fdp), money=Affiliate(tracking_code=code, merchant="acme"))
    store = Store(":memory:")
    try:
        store.insert_experiment(row)
        hit(store, code)
        hit(store, text(fdp, 8))
    except EXPECTED:
        return
    finally:
        store._conn.close()


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
