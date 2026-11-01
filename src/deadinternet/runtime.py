import os
from pathlib import Path

from deadinternet.domain.experiment import Experiment, Platform
from deadinternet.publish.registry import PublishResult, publish
from deadinternet.render.faceless import default_runner
from deadinternet.render.registry import render


class _EnvAvatar:
    def create(self, script: str, presenter_id: str, voice_id: str) -> bytes:
        if not os.environ.get("AVATAR_API_KEY"):
            raise RuntimeError("AVATAR_API_KEY is not set")
        raise RuntimeError("avatar provider call is not configured")


class LiveRenderer:
    def render(self, experiment: Experiment, media_dir: Path) -> Experiment:
        return render(
            experiment,
            media_dir,
            runner=default_runner,
            avatar_client=_EnvAvatar(),
        )


class LivePublisher:
    def publish(
        self,
        experiment: Experiment,
        platform: Platform,
        account_id: str,
        token: str | None = None,
    ) -> PublishResult:
        return publish(experiment, platform, account_id, token=token)
