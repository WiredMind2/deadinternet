from pathlib import Path

from deadinternet.domain.experiment import Experiment
from deadinternet.render.avatar import render_avatar
from deadinternet.render.faceless import Runner, Speaker, render_faceless


def render(
    experiment: Experiment,
    media_dir: Path | str,
    *,
    runner: Runner,
    avatar_client,
    speaker: Speaker | None = None,
) -> Experiment:
    kind = experiment.style.kind
    if kind == "faceless":
        return render_faceless(experiment, media_dir, runner=runner, speaker=speaker)
    if kind == "avatar":
        return render_avatar(experiment, media_dir, client=avatar_client)
    raise ValueError(f"unknown style kind {kind}")
