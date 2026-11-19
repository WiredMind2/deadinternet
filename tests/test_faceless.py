import io
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from deadinternet.domain.experiment import (
    Affiliate,
    Beat,
    Experiment,
    FacelessStyle,
    Look,
    Status,
)
from deadinternet.render import faceless, render
from deadinternet.storyboard import write_storyboard


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


def _silence(seconds: float, rate: int = 44100) -> bytes:
    """A minimal valid wav: header plus silence, stdlib only."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class _RecordingSpeaker:
    """Stands in for TTS: records each spoken line, returns tiny wavs."""

    def __init__(self, durations: tuple[float, ...] = (1.0,)):
        self.durations = durations
        self.spoken: list[str] = []

    def __call__(self, text: str) -> bytes:
        self.spoken.append(text)
        return _silence(self.durations[(len(self.spoken) - 1) % len(self.durations)])


def _beats(*spoken_on_screen: tuple[str, str]) -> tuple[Beat, ...]:
    return tuple(
        Beat(spoken=spoken, on_screen=on_screen) for spoken, on_screen in spoken_on_screen
    )


def _write_board(media_dir: Path, experiment: Experiment, beats) -> None:
    write_storyboard(media_dir / f"{experiment.id}.storyboard.json", beats)


def _font_file(tmp_path: Path, name: str = "fake-font.ttf") -> Path:
    font = tmp_path / name
    font.write_bytes(b"not a real font; only the path matters to the filter")
    return font


def _write_segments(media_dir: Path, experiment_id: str, names: tuple[str, ...]) -> None:
    segments = media_dir / f"{experiment_id}.segments"
    segments.mkdir(parents=True, exist_ok=True)
    for name in names:
        (segments / name).write_bytes(b"clip")


def test_stills_runner_writes_vertical_mp4(tmp_path: Path):
    experiment = _rendering()
    _write_board(tmp_path, experiment, _beats(("Line one.", ""), ("Line two.", "")))
    output = tmp_path / f"{experiment.id}.mp4"
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))
        output.write_bytes(b"tiny-mp4")

    result = render(
        experiment,
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker(),
    )

    assert result.status is Status.in_review
    assert Path(result.file_path) == output
    assert output.is_file()
    text = " ".join(commands[0])
    assert "1080" in text
    assert "1920" in text
    assert str(output) in commands[-1]


def test_stills_render_speaks_each_beat(tmp_path: Path):
    experiment = _rendering()
    _write_board(
        tmp_path, experiment, _beats(("First spoken line.", ""), ("Second spoken line.", ""))
    )
    speaker = _RecordingSpeaker((1.0, 1.5))
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(
        experiment, tmp_path, runner=runner, avatar_client=_UnusedAvatar(), speaker=speaker
    )

    assert result.status is Status.in_review
    # One call to the speaker per beat, with that beat's spoken line.
    assert speaker.spoken == ["First spoken line.", "Second spoken line."]
    # One segment command per beat, then the concat that joins them.
    assert len(commands) == 3
    first, second, concat = commands
    segments_dir = tmp_path / f"{experiment.id}.stills"
    assert str(segments_dir / "001.audio") in first
    assert str(segments_dir / "002.audio") in second
    # The visual spans exactly the audio: the lavfi duration and -t both come
    # from each beat's own spoken segment, never from length_sec.
    assert "color=c=black:s=1080x1920:r=30:d=1.000" in first
    assert first[first.index("-t") + 1] == "1.000"
    assert "color=c=black:s=1080x1920:r=30:d=1.500" in second
    assert second[second.index("-t") + 1] == "1.500"
    # The audio is muxed into each segment, not dropped on the floor.
    assert "aac" in first
    assert "aac" in second
    assert str(segments_dir / "concat.txt") in concat
    assert str(tmp_path / f"{experiment.id}.mp4") in concat


def test_stills_concat_listing_names_beat_segments_in_order(tmp_path: Path):
    experiment = _rendering()
    _write_board(
        tmp_path, experiment, _beats(("First spoken line.", ""), ("Second spoken line.", ""))
    )

    def runner(cmd: list[str]) -> None:
        pass

    render(
        experiment, tmp_path, runner=runner, avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker(),
    )

    listing = tmp_path / f"{experiment.id}.stills" / "concat.txt"
    assert listing.read_text(encoding="utf-8") == "file '001.mp4'\nfile '002.mp4'\n"


def test_stills_without_a_storyboard_marks_render_failed(tmp_path: Path):
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(
        _rendering(),
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker(),
    )

    assert result.status is Status.render_failed
    assert result.file_path is None
    assert "storyboard.json" in (result.render_error or "")
    assert commands == []


def test_empty_storyboard_marks_render_failed(tmp_path: Path):
    experiment = _rendering()
    _write_board(tmp_path, experiment, [])

    result = render(
        experiment,
        tmp_path,
        runner=lambda cmd: None,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker(),
    )

    assert result.status is Status.render_failed
    assert result.render_error == "storyboard needs at least one beat"


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
    experiment = _rendering()
    _write_board(tmp_path, experiment, _beats(("Line one.", "")))

    def runner(cmd: list[str]) -> None:
        raise RuntimeError("ffmpeg exploded")

    result = render(
        experiment,
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker(),
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
    experiment = _rendering()
    _write_board(tmp_path, experiment, _beats(("Line one.", "")))

    def wedged_run(cmd: list[str], **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(faceless.subprocess, "run", wedged_run)

    result = render(
        experiment,
        tmp_path,
        runner=faceless.default_runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker(),
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
        speaker=_RecordingSpeaker(),
    )

    assert result.status is Status.render_failed
    assert result.file_path is None
    assert result.render_error
    assert commands == []


def test_tts_failure_marks_render_failed(tmp_path: Path):
    experiment = _rendering()
    _write_board(tmp_path, experiment, _beats(("Line one.", "")))
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    def broken_speaker(text: str) -> bytes:
        raise RuntimeError("TTS exploded")

    result = render(
        experiment,
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=broken_speaker,
    )

    assert result.status is Status.render_failed
    assert result.render_error == "TTS exploded"
    assert result.file_path is None
    # The failure happened before any ffmpeg was started.
    assert commands == []


def test_unconfigured_tts_marks_render_failed(tmp_path: Path, monkeypatch):
    experiment = _rendering()
    _write_board(tmp_path, experiment, _beats(("Line one.", "")))
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    monkeypatch.delenv(faceless.TTS_ENV_VAR, raising=False)
    result = render(experiment, tmp_path, runner=runner, avatar_client=_UnusedAvatar())

    assert result.status is Status.render_failed
    assert result.render_error == f"TTS is not configured ({faceless.TTS_ENV_VAR})"
    assert result.file_path is None
    assert commands == []


def test_env_speaker_refuses_without_a_key(monkeypatch):
    monkeypatch.delenv(faceless.TTS_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError, match="TTS is not configured"):
        faceless.env_speaker("line")


def test_env_speaker_still_refuses_with_a_key(monkeypatch):
    # A key alone is not a provider: the live call is wired by injection, the
    # same way the avatar client is.
    monkeypatch.setenv(faceless.TTS_ENV_VAR, "secret")
    with pytest.raises(RuntimeError, match="provider call is not configured"):
        faceless.env_speaker("line")


def test_non_wav_audio_is_measured_by_ffprobe(tmp_path: Path, monkeypatch):
    experiment = _rendering()
    _write_board(tmp_path, experiment, _beats(("Line one.", "")))
    captured: dict = {}
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs):
        captured["cmd"] = list(cmd)
        captured.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="1.250\n")

    monkeypatch.setattr(faceless.subprocess, "run", fake_run)

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(
        experiment,
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=lambda text: b"not a wav",
    )

    assert result.status is Status.in_review
    assert captured["cmd"][0] == "ffprobe"
    assert str(tmp_path / f"{experiment.id}.stills" / "001.audio") in captured["cmd"]
    assert captured["timeout"] == faceless.RENDER_TIMEOUT_SEC
    beat_one = commands[0]
    assert "color=c=black:s=1080x1920:r=30:d=1.250" in beat_one
    assert beat_one[beat_one.index("-t") + 1] == "1.250"


def test_unmeasurable_audio_marks_render_failed(tmp_path: Path, monkeypatch):
    experiment = _rendering()
    _write_board(tmp_path, experiment, _beats(("Line one.", "")))
    commands: list[list[str]] = []

    def missing_ffprobe(cmd: list[str], **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(faceless.subprocess, "run", missing_ffprobe)

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(
        experiment,
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=lambda text: b"not a wav",
    )

    assert result.status is Status.render_failed
    assert "ffprobe" in result.render_error
    assert commands == []


def _bold_font_or_none() -> Path | None:
    try:
        return faceless._caption_font("bold")
    except RuntimeError:
        return None


def _caption_vf(tmp_path: Path, *, caption_style: str) -> str:
    experiment = _rendering(
        style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style=caption_style)
    )
    _write_board(tmp_path, experiment, _beats(("Line one.", "On screen line")))
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(
        experiment,
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker(),
    )

    assert result.status is Status.in_review
    return commands[0][commands[0].index("-vf") + 1]


def test_on_screen_text_is_burned_into_its_own_beat(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(faceless.CAPTION_FONT_ENV_VAR, raising=False)
    monkeypatch.setattr(faceless, "_BOLD_FONT_FILES", (str(_font_file(tmp_path)),))
    experiment = _rendering()
    _write_board(
        tmp_path,
        experiment,
        _beats(("First spoken line.", "First caption!"), ("Second spoken line.", "")),
    )
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(
        experiment,
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker((1.0, 1.0)),
    )

    assert result.status is Status.in_review
    first, second, _concat = commands
    caption_file = tmp_path / f"{experiment.id}.stills" / "001.caption.txt"
    assert caption_file.read_text(encoding="utf-8") == "First caption!"
    first_vf = first[first.index("-vf") + 1]
    assert "drawtext" in first_vf
    assert "textfile=" in first_vf
    # The caption shares its beat's exact span: the captioned command carries
    # the same -t as its own audio segment.
    assert first[first.index("-t") + 1] == "1.000"
    assert "color=c=black:s=1080x1920:r=30:d=1.000" in first
    # A beat with empty on_screen draws nothing at all.
    second_vf = second[second.index("-vf") + 1]
    assert "drawtext" not in second_vf
    assert not (tmp_path / f"{experiment.id}.stills" / "002.caption.txt").exists()


def test_caption_style_bold_changes_the_draw(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(faceless.CAPTION_FONT_ENV_VAR, raising=False)
    monkeypatch.setattr(faceless, "_BOLD_FONT_FILES", (str(_font_file(tmp_path, "b.ttf")),))
    monkeypatch.setattr(faceless, "_DEFAULT_FONT_FILES", (str(_font_file(tmp_path, "d.ttf")),))
    bold = _caption_vf(tmp_path, caption_style="bold")
    plain = _caption_vf(tmp_path, caption_style="plain")
    assert "fontsize=96:borderw=6" in bold
    assert "fontsize=72:borderw=3" in plain
    assert bold != plain


def test_caption_font_follows_the_style_candidates(tmp_path: Path, monkeypatch):
    bold_font = _font_file(tmp_path, "bold.ttf")
    plain_font = _font_file(tmp_path, "plain.ttf")
    monkeypatch.delenv(faceless.CAPTION_FONT_ENV_VAR, raising=False)
    monkeypatch.setattr(faceless, "_BOLD_FONT_FILES", (str(bold_font),))
    monkeypatch.setattr(faceless, "_DEFAULT_FONT_FILES", (str(plain_font),))
    assert faceless._caption_font("bold") == bold_font
    assert faceless._caption_font("plain") == plain_font
    assert faceless._caption_font("bold") != faceless._caption_font("plain")


def test_caption_font_env_override_is_honoured(tmp_path: Path, monkeypatch):
    font = _font_file(tmp_path)
    monkeypatch.setenv(faceless.CAPTION_FONT_ENV_VAR, str(font))
    assert faceless._caption_font("bold") == font


def test_absent_caption_font_env_override_fails_clearly(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(faceless.CAPTION_FONT_ENV_VAR, str(tmp_path / "absent.ttf"))
    with pytest.raises(RuntimeError, match="is not a file"):
        faceless._caption_font("bold")


def test_missing_caption_font_marks_render_failed(tmp_path: Path, monkeypatch):
    experiment = _rendering()
    _write_board(tmp_path, experiment, _beats(("Line one.", "Caption text")))
    monkeypatch.delenv(faceless.CAPTION_FONT_ENV_VAR, raising=False)
    monkeypatch.setattr(faceless, "_BOLD_FONT_FILES", (str(tmp_path / "absent.ttf"),))
    commands: list[list[str]] = []

    def runner(cmd: list[str]) -> None:
        commands.append(list(cmd))

    result = render(
        experiment,
        tmp_path,
        runner=runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker(),
    )

    assert result.status is Status.render_failed
    assert "no caption font" in result.render_error
    assert faceless.CAPTION_FONT_ENV_VAR in result.render_error
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


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg is not installed",
)
def test_stills_render_length_is_the_sum_of_segments_with_real_ffmpeg(tmp_path: Path):
    experiment = _rendering()
    _write_board(
        tmp_path, experiment, _beats(("One second of speech.", ""), ("One and a half.", ""))
    )

    result = render(
        experiment,
        tmp_path,
        runner=faceless.default_runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker((1.0, 1.5)),
    )

    assert result.status is Status.in_review
    output = tmp_path / f"{experiment.id}.mp4"
    assert Path(result.file_path) == output
    probed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    length = float(probed.stdout.strip())
    assert abs(length - 2.5) < 0.25


def _gray_frame(output: Path, at: str) -> bytes:
    frame = output.with_suffix(".frame.gray")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            at,
            "-i",
            str(output),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            str(frame),
        ],
        check=True,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    return frame.read_bytes()


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg is not installed",
)
@pytest.mark.skipif(_bold_font_or_none() is None, reason="no caption font on this machine")
def test_captions_are_burned_into_their_own_beat_with_real_ffmpeg(tmp_path: Path):
    experiment = _rendering()
    _write_board(
        tmp_path,
        experiment,
        _beats(
            ("It's one hundred percent.", "It's 100%: the 'quoted' text"),
            ("Second beat.", ""),
        ),
    )

    result = render(
        experiment,
        tmp_path,
        runner=faceless.default_runner,
        avatar_client=_UnusedAvatar(),
        speaker=_RecordingSpeaker((1.0, 1.0)),
    )

    assert result.status is Status.in_review
    output = tmp_path / f"{experiment.id}.mp4"
    captioned = _gray_frame(output, "0.5")
    plain = _gray_frame(output, "1.5")
    # Inside beat one the caption drew pixels; inside beat two nothing did.
    assert max(captioned) > 0
    assert max(plain) == 0
