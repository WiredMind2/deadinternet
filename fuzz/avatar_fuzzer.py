"""Fuzz avatar rendering with an in-process client. No network call."""
import sys
from dataclasses import replace
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "fuzz"))

from corpus import experiment_from, text  # noqa: E402
from deadinternet.domain.experiment import AvatarStyle, Status  # noqa: E402
from deadinternet.render.avatar import render_avatar  # noqa: E402


class _Client:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def create(self, script: str, presenter_id: str, voice_id: str) -> bytes:
        return self.payload


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    row = replace(
        experiment_from(fdp),
        status=Status.rendering,
        style=AvatarStyle(presenter_id=text(fdp, 8), voice_id=text(fdp, 8)),
    )
    render_avatar(row, Path("/tmp/deadinternet-fuzz"), client=_Client(fdp.ConsumeBytes(32)))


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
