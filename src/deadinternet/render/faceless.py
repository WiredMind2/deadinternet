import io
import os
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path

from deadinternet.domain.experiment import (
    Beat,
    Experiment,
    InvalidBoard,
    Look,
    mark_render_failed,
    mark_rendered,
)
from deadinternet.storyboard import read_storyboard

Runner = Callable[[list[str]], None]
Speaker = Callable[[str], bytes]

RENDER_TIMEOUT_SEC = 10 * 60

# Env gates mirror the avatar provider (runtime.py): without a provider the
# render fails with a reason instead of shipping a silent black file.
TTS_ENV_VAR = "DEADINTERNET_TTS_API_KEY"
CAPTION_FONT_ENV_VAR = "DEADINTERNET_CAPTION_FONT"

# "bold" is the only caption_style value the domain names today
# (domain/rank.py); it draws with a heavier face and border. Any other value
# keeps the default look instead of inventing a new factor level.
_BOLD_FONT_FILES = (
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)
_DEFAULT_FONT_FILES = (
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


def default_runner(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, timeout=RENDER_TIMEOUT_SEC)


def env_speaker(text: str) -> bytes:
    if not os.environ.get(TTS_ENV_VAR):
        raise RuntimeError(f"TTS is not configured ({TTS_ENV_VAR})")
    raise RuntimeError("TTS provider call is not configured")


def render_faceless(
    experiment: Experiment,
    media_dir: Path | str,
    *,
    runner: Runner = default_runner,
    speaker: Speaker | None = None,
) -> Experiment:
    output = Path(media_dir) / f"{experiment.id}.mp4"
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        commands = _ffmpeg_commands(
            experiment, output, speaker=env_speaker if speaker is None else speaker
        )
    except ValueError:
        # An unknown look is a programming error, not a render failure.
        raise
    except Exception as exc:
        return mark_render_failed(experiment, str(exc))
    try:
        for command in commands:
            runner(command)
    except Exception as exc:
        return mark_render_failed(experiment, str(exc))
    return mark_rendered(experiment, str(output))


def _ffmpeg_commands(
    experiment: Experiment, output: Path, *, speaker: Speaker
) -> list[list[str]]:
    look = experiment.style.look
    if look is Look.stills:
        return _stills_commands(experiment, output, speaker=speaker)
    if look is Look.clips:
        return [_concat_command(experiment, output)]
    raise ValueError(f"unknown look {look}")


def _stills_commands(
    experiment: Experiment, output: Path, *, speaker: Speaker
) -> list[list[str]]:
    # The approved board is the source of beats at render time: the API only
    # renders a board_approved row, and it passes the storyboard's own
    # directory as the media dir.
    beats, _digest = read_storyboard(output.parent / f"{experiment.id}.storyboard.json")
    if not beats:
        raise InvalidBoard("storyboard needs at least one beat")
    segments_dir = output.with_suffix(".stills")
    segments_dir.mkdir(parents=True, exist_ok=True)
    caption_style = experiment.style.caption_style
    commands: list[list[str]] = []
    names: list[str] = []
    for index, beat in enumerate(beats, start=1):
        stem = f"{index:03d}"
        audio = segments_dir / f"{stem}.audio"
        payload = speaker(beat.spoken)
        audio.write_bytes(payload)
        # Each beat's visual spans exactly its audio segment, so the file's
        # length is the sum of the spoken segments, never length_sec.
        duration = _segment_duration(payload, audio)
        commands.append(
            _beat_command(
                beat,
                caption_style=caption_style,
                duration=duration,
                audio=audio,
                segment=segments_dir / f"{stem}.mp4",
            )
        )
        names.append(f"file '{stem}.mp4'\n")
    listing = segments_dir / "concat.txt"
    listing.write_text("".join(names), encoding="utf-8")
    commands.append(_concat_run(listing, output))
    return commands


def _beat_command(
    beat: Beat,
    *,
    caption_style: str,
    duration: float,
    audio: Path,
    segment: Path,
) -> list[str]:
    filters = ["scale=1080:1920", "format=yuv420p"]
    if beat.on_screen:
        caption = segment.with_suffix(".caption.txt")
        caption.write_text(beat.on_screen, encoding="utf-8")
        filters.append(_caption_filter(caption, caption_style))
    sized = f"{duration:.3f}"
    return [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s=1080x1920:r=30:d={sized}",
        "-i",
        str(audio),
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-t",
        sized,
        str(segment),
    ]


def _caption_filter(caption: Path, caption_style: str) -> str:
    font = _caption_font(caption_style)
    if font is None:
        raise RuntimeError(
            f"no caption font for caption_style {caption_style!r};"
            f" set {CAPTION_FONT_ENV_VAR}"
        )
    if caption_style == "bold":
        sizing = "fontsize=96:borderw=6"
    else:
        sizing = "fontsize=72:borderw=3"
    return ":".join(
        [
            # textfile keeps the on-screen line out of filtergraph parsing:
            # no quoting of apostrophes, colons or percents, and
            # expansion=none stops drawtext reading %{} sequences in it.
            f"drawtext=textfile={_filter_value(caption)}",
            f"fontfile={_filter_value(font)}",
            "expansion=none",
            sizing,
            "fontcolor=white",
            "bordercolor=black",
            "x=(w-text_w)/2",
            "y=(h-text_h)/2",
        ]
    )


def _filter_value(path: Path) -> str:
    # The documented fontfile recipe: quote the whole value, and escape the
    # drive colon, which splits options even inside a quoted section.
    return "'" + path.as_posix().replace(":", "\\:") + "'"


def _caption_font(caption_style: str) -> Path | None:
    override = os.environ.get(CAPTION_FONT_ENV_VAR)
    if override:
        font = Path(override)
        if not font.is_file():
            raise RuntimeError(f"{CAPTION_FONT_ENV_VAR} is not a file: {override}")
        return font
    candidates = _BOLD_FONT_FILES if caption_style == "bold" else _DEFAULT_FONT_FILES
    for candidate in candidates:
        if Path(candidate).is_file():
            return Path(candidate)
    return None


def _segment_duration(payload: bytes, audio: Path) -> float:
    try:
        # wave rejects bad headers (including a zero frame rate) itself.
        with wave.open(io.BytesIO(payload)) as wav:
            return wav.getnframes() / wav.getframerate()
    except (EOFError, wave.Error):
        # A speaker may hand back mp3 or another container: ffprobe, which
        # ships beside ffmpeg, measures those too.
        return _ffprobe_duration(audio)


def _ffprobe_duration(audio: Path) -> float:
    try:
        probed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio),
            ],
            check=True,
            capture_output=True,
            text=True,
            # The probe never reads stdin: detaching from the parent's
            # console state keeps the call robust from a service or a
            # test harness whose own stdio handles are not inheritable.
            stdin=subprocess.DEVNULL,
            timeout=RENDER_TIMEOUT_SEC,
        )
        return float(probed.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError(f"ffprobe could not measure audio segment {audio.name}") from exc


def _concat_command(experiment: Experiment, output: Path) -> list[str]:
    segments_dir = output.with_suffix(".segments")
    segments = sorted(path for path in segments_dir.glob("*.mp4") if path.is_file())
    if not segments:
        raise FileNotFoundError(f"clips look has no segment files in {segments_dir}")
    listing = output.with_suffix(".concat.txt")
    entries = (
        f"file '{segment.relative_to(listing.parent).as_posix()}'\n" for segment in segments
    )
    listing.write_text("".join(entries), encoding="utf-8")
    return _concat_run(listing, output)


def _concat_run(listing: Path, output: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-c",
        "copy",
        str(output),
    ]
