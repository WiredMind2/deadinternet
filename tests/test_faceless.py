from pathlib import Path

from deadinternet.domain.experiment import (
    Affiliate,
    Experiment,
    FacelessStyle,
    Look,
    Status,
)
from deadinternet.render import render


def _rendering(**overrides) -> Experiment:
    base = dict(
        id="exp-1",
        niche_id="niche-1",
        hypothesis="A question hook travels",
        hook_id="question",
        script="Here is the spoken script.",
        caption="Watch this.",
        style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style="bold"),
        money=Affiliate(tracking_code="abc", merchant="acme"),
        status=Status.rendering,
        length_sec=45,
    )
    base.update(overrides)
    return Experiment(**base)


class _UnusedAvatar:
    def create(self, script, presenter_id, voice_id):
        raise AssertionError("avatar client should not render a faceless experiment")


def test_stills_runner_writes_vertical_mp4(tmp_path: Path):
    experiment = _rendering()
    output = tmp_path / f"{experiment.id}.mp4"
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))
        output.write_bytes(b"tiny-mp4")

    result = render(experiment, tmp_path, runner=runner, avatar_client=_UnusedAvatar())

    assert result.status is Status.in_review
    assert Path(result.file_path) == output
    assert output.is_file()
    text = " ".join(commands[0])
    assert "1080" in text
    assert "1920" in text
    assert str(output) in commands[0]


def test_clips_runner_is_asked_to_concatenate(tmp_path: Path):
    experiment = _rendering(
        style=FacelessStyle(look=Look.clips, voice_id="voice-1", caption_style="bold")
    )
    output = tmp_path / f"{experiment.id}.mp4"
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))
        output.write_bytes(b"tiny-mp4")

    result = render(experiment, tmp_path, runner=runner, avatar_client=_UnusedAvatar())

    assert result.status is Status.in_review
    assert output.is_file()
    assert "concat" in commands[0]


def test_runner_exception_marks_render_failed(tmp_path: Path):
    def runner(cmd: list[str]) -> None:
        raise RuntimeError("ffmpeg exploded")

    result = render(
        _rendering(),
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
    )

    assert result.status is Status.render_failed
    assert result.render_error == "ffmpeg exploded"
    assert result.file_path is None
