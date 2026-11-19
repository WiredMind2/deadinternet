from fastapi.testclient import TestClient

from deadinternet.api import create_app
from deadinternet.domain.experiment import Platform, Publication, PublicationStatus
from deadinternet.metrics.pull import record_snapshot
from tests.helpers import experiment, open_store


def _publication(store, publication_id="pub-1") -> Publication:
    store.insert_experiment(experiment(id="exp-1"))
    return store.add_publication(
        Publication(
            id=publication_id,
            experiment_id="exp-1",
            platform=Platform.tiktok,
            account_id="acct-1",
            status=PublicationStatus.posted,
            post_url=f"https://tiktok.example/{publication_id}",
        )
    )


def test_failed_snapshot_does_not_add_a_row(tmp_path):
    store = open_store(tmp_path)
    publication = _publication(store)
    failed = {
        "failed": True,
        "views": 0,
        "watch_time_seconds": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
    }
    record_snapshot(store, publication.id, failed)
    assert store.list_snapshots(publication.id) == []

    record_snapshot(
        store,
        publication.id,
        {
            "views": 10,
            "watch_time_seconds": 4,
            "likes": 1,
            "comments": 0,
            "shares": 0,
            "captured_at": "2026-10-31T00:00:00Z",
        },
    )
    assert store.list_snapshots(publication.id) == [
        {
            "publication_id": publication.id,
            "captured_at": "2026-10-31T00:00:00Z",
            "views": 10,
            "watch_time_seconds": 4,
            "likes": 1,
            "comments": 0,
            "shares": 0,
        }
    ]

    with TestClient(create_app(store)) as client:
        response = client.post(
            "/snapshots",
            json={"publication_id": publication.id, "views": 0, "failed": True},
        )
    assert response.status_code == 200
    assert len(store.list_snapshots(publication.id)) == 1


def test_snapshot_for_an_unknown_publication_is_404(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        response = client.post("/snapshots", json={"publication_id": "pub-missing", "views": 5})
    assert response.status_code == 404
    assert store.list_snapshots("pub-missing") == []


def test_negative_snapshot_counts_are_refused(tmp_path):
    store = open_store(tmp_path)
    publication = _publication(store)
    with TestClient(create_app(store)) as client:
        for payload in (
            {"views": -1},
            {"watch_time_seconds": -5},
            {"likes": -2},
            {"comments": -1},
            {"shares": -3},
        ):
            response = client.post(
                "/snapshots", json={"publication_id": publication.id, **payload}
            )
            assert response.status_code == 422, payload
    assert store.list_snapshots(publication.id) == []
