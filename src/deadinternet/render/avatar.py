from pathlib import Path

from deadinternet.domain.experiment import Experiment, mark_render_failed, mark_rendered


def render_avatar(experiment: Experiment, media_dir: Path | str, *, client) -> Experiment:
    output = Path(media_dir) / f"{experiment.id}.mp4"
    try:
        payload = client.create(
            experiment.script,
            experiment.style.presenter_id,
            experiment.style.voice_id,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    except Exception as exc:
        return mark_render_failed(experiment, str(exc))
    return mark_rendered(experiment, str(output))
