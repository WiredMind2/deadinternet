import subprocess
from collections.abc import Callable
from pathlib import Path

from deadinternet.domain.experiment import Experiment, Look, mark_render_failed, mark_rendered

Runner = Callable[[list[str]], None]

RENDER_TIMEOUT_SEC = 10 * 60


def default_runner(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, timeout=RENDER_TIMEOUT_SEC)


def render_faceless(
    experiment: Experiment,
    media_dir: Path | str,
    *,
    runner: Runner = default_runner,
) -> Experiment:
    output = Path(media_dir) / f"{experiment.id}.mp4"
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        command = _ffmpeg_command(experiment, output)
    except ValueError:
        # An unknown look is a programming error, not a render failure.
        raise
    except Exception as exc:
        return mark_render_failed(experiment, str(exc))
    try:
        runner(command)
    except Exception as exc:
        return mark_render_failed(experiment, str(exc))
    return mark_rendered(experiment, str(output))


def _ffmpeg_command(experiment: Experiment, output: Path) -> list[str]:
    look = experiment.style.look
    if look is Look.stills:
        return _stills_command(experiment, output)
    if look is Look.clips:
        return _concat_command(experiment, output)
    raise ValueError(f"unknown look {look}")


def _stills_command(experiment: Experiment, output: Path) -> list[str]:
    duration = str(experiment.length_sec)
    return [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s=1080x1920:r=30:d={duration}",
        "-vf",
        "scale=1080:1920,format=yuv420p",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-t",
        duration,
        str(output),
    ]


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
