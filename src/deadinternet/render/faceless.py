import subprocess
from collections.abc import Callable
from pathlib import Path

from deadinternet.domain.experiment import Experiment, Look, mark_render_failed, mark_rendered

Runner = Callable[[list[str]], None]


def default_runner(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def render_faceless(
    experiment: Experiment,
    media_dir: Path | str,
    *,
    runner: Runner = default_runner,
) -> Experiment:
    output = Path(media_dir) / f"{experiment.id}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = _ffmpeg_command(experiment, output)
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
        return _concat_command(output)
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


def _concat_command(output: Path) -> list[str]:
    listing = output.with_suffix(".concat.txt")
    listing.write_text("", encoding="utf-8")
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
