"""Fuzz proposal parsing and the starter grid."""
import sys
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "fuzz"))

from corpus import EXPECTED, catalog_for, experiment_from, proposal_raw  # noqa: E402
from deadinternet.domain.proposal import parse_proposal, starter_grid  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    row = experiment_from(fdp)
    presenter = row.style.presenter_id if hasattr(row.style, "presenter_id") else "presenter"
    try:
        parse_proposal([proposal_raw(fdp, row)], catalog_for(row))
        starter_grid([row.niche_id], row.money, row.hook_id, row.style.voice_id, presenter)
    except EXPECTED:
        return


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
