import pytest

from deadinternet.domain.experiment import (
    Affiliate,
    Experiment,
    FacelessStyle,
    InvalidTransition,
    Look,
    Platform,
    PublicationStatus,
    Status,
)
from deadinternet.publish import ManualPack, PublishRefused, publish


def _row(**overrides) -> Experiment:
    base = dict(
        id="exp-1",
        niche_id="niche-1",
        hypothesis="A question hook travels",
        hook_id="question",
        script="Here is the spoken script.",
        caption="Watch this.",
        style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style="bold"),
        money=Affiliate(tracking_code="abc", merchant="acme"),
        status=Status.approved,
        length_sec=45,
        file_path="data/videos/exp-1.mp4",
    )
    base.update(overrides)
    return Experiment(**base)


class FakeClient:
    def __init__(self, url="https://cdn.example/v/1", fail_platforms=()):
        self.url = url
        self.fail_platforms = set(fail_platforms)
        self.calls = []

    def post(self, platform, token, experiment, disclosure):
        self.calls.append(
            {
                "platform": platform,
                "token": token,
                "experiment": experiment,
                "disclosure": disclosure,
            }
        )
        if platform in self.fail_platforms:
            raise RuntimeError(f"{platform.value} upload failed")
        return self.url


def test_in_review_is_refused(monkeypatch):
    called = []
    monkeypatch.setattr(
        "deadinternet.publish.registry.mark_posted",
        lambda experiment: called.append(experiment),
    )
    client = FakeClient()
    with pytest.raises((PublishRefused, InvalidTransition)):
        publish(
            _row(status=Status.in_review),
            Platform.tiktok,
            "acct-1",
            token="tok",
            client=client,
        )
    assert called == []
    assert client.calls == []


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_token_yields_manual_pack(token):
    experiment = _row()
    client = FakeClient()
    result = publish(
        experiment,
        Platform.instagram,
        "acct-ig",
        token=token,
        client=client,
    )
    assert result.publication.status is PublicationStatus.manual_needed
    assert result.publication.post_url is None
    assert result.publication.error is None
    assert result.publication.experiment_id == experiment.id
    assert result.publication.account_id == "acct-ig"
    assert result.publication.platform is Platform.instagram
    assert result.manual_pack == ManualPack(
        file_path=experiment.file_path,
        caption=experiment.caption,
        platform=Platform.instagram,
    )
    assert client.calls == []


@pytest.mark.parametrize(
    "platform,key",
    [
        (Platform.tiktok, "is_aigc"),
        (Platform.instagram, "is_ai_generated"),
        (Platform.youtube, "containsSyntheticMedia"),
    ],
)
def test_success_posts_url_and_sends_disclosure(platform, key):
    experiment = _row()
    client = FakeClient(url="https://cdn.example/v/1")
    result = publish(
        experiment,
        platform,
        "acct-1",
        token="secret-token",
        client=client,
    )
    assert result.publication.status is PublicationStatus.posted
    assert result.publication.post_url == "https://cdn.example/v/1"
    assert result.publication.error is None
    assert result.manual_pack is None
    assert client.calls[0]["token"] == "secret-token"
    disclosure = client.calls[0]["disclosure"]
    assert disclosure["contains_synthetic"] is True
    assert disclosure[key] is True


def test_failure_leaves_the_other_platform_independent():
    experiment = _row()
    client = FakeClient(
        url="https://youtube.example/shorts/1",
        fail_platforms={Platform.tiktok},
    )
    failed = publish(
        experiment,
        Platform.tiktok,
        "acct-tt",
        token="tok",
        client=client,
    )
    posted = publish(
        experiment,
        Platform.youtube,
        "acct-yt",
        token="tok",
        client=client,
    )
    assert failed.publication.status is PublicationStatus.failed
    assert failed.publication.error == "tiktok upload failed"
    assert failed.publication.post_url is None
    assert failed.publication.platform is Platform.tiktok
    assert failed.manual_pack is None
    assert posted.publication.status is PublicationStatus.posted
    assert posted.publication.post_url == "https://youtube.example/shorts/1"
    assert posted.publication.platform is Platform.youtube
    assert posted.publication.id != failed.publication.id
    assert client.calls[1]["disclosure"]["containsSyntheticMedia"] is True


def test_live_experiment_can_be_posted():
    client = FakeClient(url="https://cdn.example/live")
    result = publish(
        _row(status=Status.live),
        Platform.tiktok,
        "acct-1",
        token="tok",
        client=client,
    )
    assert result.publication.status is PublicationStatus.posted
    assert result.publication.post_url == "https://cdn.example/live"
