from pathlib import Path

from deadinternet.domain.experiment import (
    Affiliate,
    AvatarStyle,
    Experiment,
    Status,
)
from deadinternet.render import render


def _rendering(**overrides) -> Experiment:
    base = dict(
        id="exp-1",
        niche_id="niche-1",
        hypothesis="A presenter holds attention",
        hook_id="question",
        script="Here is the spoken script.",
        caption="Watch this.",
        style=AvatarStyle(presenter_id="presenter-9", voice_id="voice-9"),
        money=Affiliate(tracking_code="abc", merchant="acme"),
        status=Status.rendering,
        length_sec=45,
    )
    base.update(overrides)
    return Experiment(**base)


def _runner(cmd: list[str]) -> None:
    raise AssertionError("ffmpeg runner should not render an avatar experiment")


def test_avatar_client_bytes_are_the_mp4(tmp_path: Path):
    experiment = _rendering()
    seen: list[tuple[str, str, str]] = []

    class Client:
        def create(self, script, presenter_id, voice_id) -> bytes:
            seen.append((script, presenter_id, voice_id))
            return b"fake-mp4"

    result = render(experiment, tmp_path, runner=_runner, avatar_client=Client())
    output = tmp_path / f"{experiment.id}.mp4"

    assert result.status is Status.in_review
    assert Path(result.file_path) == output
    assert output.read_bytes() == b"fake-mp4"
    assert seen == [(experiment.script, "presenter-9", "voice-9")]


def test_avatar_client_exception_marks_render_failed(tmp_path: Path):
    class Client:
        def create(self, script, presenter_id, voice_id) -> bytes:
            raise RuntimeError("presenter offline")

    result = render(
        _rendering(),
        tmp_path,
        runner=_runner,
        avatar_client=Client(),
    )

    assert result.status is Status.render_failed
    assert result.render_error == "presenter offline"
    assert result.file_path is None
