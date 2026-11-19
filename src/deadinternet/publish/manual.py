from dataclasses import dataclass

from deadinternet.domain.experiment import Platform


@dataclass(frozen=True)
class ManualPack:
    """Operator handoff when a platform token is missing."""

    experiment_id: str
    account_id: str
    file_path: str | None
    caption: str
    script: str
    platform: Platform
