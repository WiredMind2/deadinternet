"""Fuzz publishing. The client checks AI disclosure and does not call a network."""
import sys
from dataclasses import replace
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "fuzz"))

from corpus import EXPECTED, experiment_from, pick, text  # noqa: E402
from deadinternet.domain.experiment import Platform, Status  # noqa: E402
from deadinternet.publish.registry import publish  # noqa: E402

_FIELD = {
    Platform.tiktok: "is_aigc",
    Platform.instagram: "is_ai_generated",
    Platform.youtube: "containsSyntheticMedia",
}


class _Client:
    def __init__(self, url: str) -> None:
        self.url = url

    def post(self, platform, token: str, experiment, disclosure: dict) -> str:
        if disclosure.get("contains_synthetic") is not True:
            raise AssertionError("contains_synthetic")
        field = _FIELD[platform]
        if disclosure.get(field) is not True:
            raise AssertionError(field)
        return self.url


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    row = replace(experiment_from(fdp), status=Status.approved, file_path="clip.mp4")
    token = text(fdp, 8) if fdp.ConsumeBool() else None
    try:
        publish(
            row,
            pick(fdp, list(Platform)),
            text(fdp, 8),
            token=token,
            client=_Client("https://example.test/" + text(fdp, 8)),
        )
    except EXPECTED:
        return


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
