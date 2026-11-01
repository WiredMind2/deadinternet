"""Fuzz status transitions with real experiments."""
import sys
from dataclasses import replace
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "fuzz"))

from corpus import EXPECTED, experiment_from, text  # noqa: E402
from deadinternet.domain.experiment import (  # noqa: E402
    Event,
    Status,
    approve,
    mark_render_failed,
    mark_rendered,
    reject,
    request_render,
    transition,
)


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    row = experiment_from(fdp)
    try:
        transition(row, pick_event(fdp))
        request_render(row, fdp.ConsumeIntInRange(0, 12), cap=fdp.ConsumeIntInRange(1, 12))
        rendering = replace(row, status=Status.rendering)
        mark_rendered(rendering, text(fdp))
        mark_render_failed(rendering, text(fdp))
        approve(row, "2026-01-01T00:00:00Z")
        reject(row)
    except EXPECTED:
        return


def pick_event(fdp):
    return list(Event)[fdp.ConsumeIntInRange(0, len(Event) - 1)]


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
