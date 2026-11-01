from dataclasses import dataclass

from deadinternet.domain.experiment import Platform


@dataclass(frozen=True)
class ManualPack:
    """Operator handoff when a platform token is missing."""

    file_path: str | None
    caption: str
    platform: Platform
