import shutil
import subprocess
from pathlib import Path

import pytest

from deadinternet.domain.experiment import (
    Affiliate,
    Experiment,
    FacelessStyle,
    Look,
    Status,
)
from deadinternet.render import faceless, render


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


def _write_segments(media_dir: Path, experiment_id: str, names: tuple[str, ...]) -> None:
    segments = media_dir / f"{experiment_id}.segments"
    segments.mkdir(parents=True, exist_ok=True)
    for name in names:
        (segments / name).write_bytes(b"clip")


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
    _write_segments(tmp_path, experiment.id, ("001.mp4", "002.mp4"))
    output = tmp_path / f"{experiment.id}.mp4"
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))
        output.write_bytes(b"tiny-mp4")

    result = render(experiment, tmp_path, runner=runner, avatar_client=_UnusedAvatar())

    assert result.status is Status.in_review
    assert output.is_file()
    assert "concat" in commands[0]


def test_clips_listing_names_segments_in_order(tmp_path: Path):
    experiment = _rendering(
        style=FacelessStyle(look=Look.clips, voice_id="voice-1", caption_style="bold")
    )
    _write_segments(tmp_path, experiment.id, ("002.mp4", "001.mp4", "003.mp4"))
    output = tmp_path / f"{experiment.id}.mp4"
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))
        output.write_bytes(b"tiny-mp4")

    result = render(experiment, tmp_path, runner=runner, avatar_client=_UnusedAvatar())

    assert result.status is Status.in_review
    listing = tmp_path / f"{experiment.id}.concat.txt"
    assert str(listing) in commands[0]
    assert listing.read_text(encoding="utf-8") == "".join(
        f"file '{experiment.id}.segments/{name}'\n"
        for name in ("001.mp4", "002.mp4", "003.mp4")
    )


def test_clips_without_segments_marks_render_failed(tmp_path: Path):
    experiment = _rendering(
        style=FacelessStyle(look=Look.clips, voice_id="voice-1", caption_style="bold")
    )
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(experiment, tmp_path, runner=runner, avatar_client=_UnusedAvatar())

    assert result.status is Status.render_failed
    assert result.file_path is None
    assert f"{experiment.id}.segments" in result.render_error
    assert commands == []
    assert not (tmp_path / f"{experiment.id}.concat.txt").exists()


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


def test_default_runner_bounds_ffmpeg_run(monkeypatch):
    captured: dict = {}

    def fake_run(cmd: list[str], **kwargs):
        captured["cmd"] = list(cmd)
        captured.update(kwargs)

    monkeypatch.setattr(faceless.subprocess, "run", fake_run)

    faceless.default_runner(["ffmpeg", "-y"])

    assert captured["cmd"] == ["ffmpeg", "-y"]
    assert faceless.RENDER_TIMEOUT_SEC > 0
    assert captured["timeout"] == faceless.RENDER_TIMEOUT_SEC


def test_wedged_ffmpeg_times_out_to_render_failed(tmp_path: Path, monkeypatch):
    def wedged_run(cmd: list[str], **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(faceless.subprocess, "run", wedged_run)

    result = render(
        _rendering(),
        tmp_path,
        runner=faceless.default_runner,
        avatar_client=_UnusedAvatar(),
    )

    assert result.status is Status.render_failed
    assert result.file_path is None
    assert "timed out" in result.render_error


def test_blocked_media_dir_marks_render_failed(tmp_path: Path):
    blocker = tmp_path / "occupied.txt"
    blocker.write_text("not a directory", encoding="utf-8")
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(
        _rendering(),
        blocker / "media",
        runner=runner,
        avatar_client=_UnusedAvatar(),
    )

    assert result.status is Status.render_failed
    assert result.file_path is None
    assert result.render_error
    assert commands == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_clips_render_succeeds_with_real_ffmpeg(tmp_path: Path):
    experiment = _rendering(
        style=FacelessStyle(look=Look.clips, voice_id="voice-1", caption_style="bold")
    )
    segments = tmp_path / f"{experiment.id}.segments"
    segments.mkdir()
    for name in ("001.mp4", "002.mp4"):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=1080x1920:r=30:d=1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(segments / name),
            ],
            check=True,
            timeout=120,
        )

    result = render(
        experiment,
        tmp_path,
        runner=faceless.default_runner,
        avatar_client=_UnusedAvatar(),
    )

    assert result.status is Status.in_review
    output = tmp_path / f"{experiment.id}.mp4"
    assert Path(result.file_path) == output
    assert output.is_file()
    assert output.stat().st_size > 0
