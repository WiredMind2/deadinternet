"""Fuzz ranking and the next-draft suggestion."""
import sys
from dataclasses import replace
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "fuzz"))

from corpus import EXPECTED, catalog_for, experiment_from  # noqa: E402
from deadinternet.domain.experiment import Status  # noqa: E402
from deadinternet.domain.rank import assert_no_render_side_effect, below_sample_floor, cell_size, suggest  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    row = replace(experiment_from(fdp), status=Status.complete)
    cell_size([row], row)
    below_sample_floor(fdp.ConsumeIntInRange(0, 6))
    assert_no_render_side_effect()
    try:
        suggest([row], catalog_for(row))
    except EXPECTED:
        return


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
