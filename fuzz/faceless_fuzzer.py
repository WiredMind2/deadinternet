"""Fuzz the faceless ffmpeg command builder. The runner does not execute ffmpeg."""
import sys
from dataclasses import replace
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "fuzz"))

from corpus import EXPECTED, experiment_from, text  # noqa: E402
from deadinternet.domain.experiment import FacelessStyle, Look, Status  # noqa: E402
from deadinternet.render.faceless import render_faceless  # noqa: E402


def _runner(cmd: list[str]) -> None:
    if not cmd or cmd[0] != "ffmpeg":
        raise AssertionError(cmd)


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    look = list(Look)[fdp.ConsumeIntInRange(0, len(Look) - 1)]
    row = replace(
        experiment_from(fdp),
        status=Status.rendering,
        style=FacelessStyle(look=look, voice_id=text(fdp, 8), caption_style="bold"),
    )
    try:
        render_faceless(row, Path("/tmp/deadinternet-fuzz"), runner=_runner)
    except EXPECTED:
        return


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
