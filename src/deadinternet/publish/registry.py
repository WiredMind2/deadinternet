from dataclasses import dataclass
from uuid import uuid4

from deadinternet.domain.experiment import (
    Experiment,
    InvalidTransition,
    Platform,
    Publication,
    PublicationStatus,
    Status,
    mark_posted,
)
from deadinternet.publish.manual import ManualPack

# Platform field that must be true on the post call so the network labels the video as AI.
_DISCLOSURE_FIELD = {
    Platform.tiktok: "is_aigc",
    Platform.instagram: "is_ai_generated",
    Platform.youtube: "containsSyntheticMedia",
}


class PublishRefused(InvalidTransition):
    """The experiment is not approved or live, so it cannot be published."""


@dataclass(frozen=True)
class PublishResult:
    publication: Publication
    manual_pack: ManualPack | None


def publish(
    experiment: Experiment,
    platform: Platform,
    account_id: str,
    *,
    token: str | None,
    client=None,
) -> PublishResult:
    """Post one approved experiment to one platform.

    ``client.post(platform, token, experiment, disclosure)`` receives
    ``disclosure`` with ``contains_synthetic`` true and the platform flag
    (``is_aigc``, ``is_ai_generated``, or ``containsSyntheticMedia``).
    A missing token does not call the client. One call never writes another
    platform's publication.
    """
    platform = platform if isinstance(platform, Platform) else Platform(platform)
    if experiment.status is not Status.approved and experiment.status is not Status.live:
        raise PublishRefused(f"{experiment.status.value} cannot be published")

    if _token_missing(token):
        return PublishResult(
            publication=_publication(
                experiment,
                platform,
                account_id,
                status=PublicationStatus.manual_needed,
            ),
            manual_pack=ManualPack(
                file_path=experiment.file_path,
                caption=experiment.caption,
                platform=platform,
            ),
        )

    if client is None:
        raise PublishRefused("a posting client is required when a token is present")

    disclosure = {
        "contains_synthetic": True,
        _DISCLOSURE_FIELD[platform]: True,
    }
    try:
        post_url = client.post(platform, token, experiment, disclosure)
    except Exception as exc:
        return PublishResult(
            publication=_publication(
                experiment,
                platform,
                account_id,
                status=PublicationStatus.failed,
                error=str(exc),
            ),
            manual_pack=None,
        )

    mark_posted(experiment)
    return PublishResult(
        publication=_publication(
            experiment,
            platform,
            account_id,
            status=PublicationStatus.posted,
            post_url=post_url,
        ),
        manual_pack=None,
    )


def _token_missing(token: str | None) -> bool:
    return token is None or token.strip() == ""


def _publication(
    experiment: Experiment,
    platform: Platform,
    account_id: str,
    *,
    status: PublicationStatus,
    post_url: str | None = None,
    error: str | None = None,
) -> Publication:
    return Publication(
        id=str(uuid4()),
        experiment_id=experiment.id,
        platform=platform,
        account_id=account_id,
        status=status,
        post_url=post_url,
        error=error,
    )
