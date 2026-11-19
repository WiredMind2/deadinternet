from fastapi.testclient import TestClient

from deadinternet.api import create_app
from deadinternet.domain.experiment import Platform, Publication, PublicationStatus
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


def test_snapshot_history_is_returned_newest_first(tmp_path):
    store = open_store(tmp_path)
    publication = _publication(store)
    with TestClient(create_app(store)) as client:
        first = client.post(
            "/snapshots",
            json={
                "publication_id": publication.id,
                "views": 10,
                "watch_time_seconds": 300,
                "likes": 2,
                "comments": 1,
                "shares": 4,
                "captured_at": "2026-11-01T00:00:00Z",
            },
        )
        assert first.status_code == 200
        second = client.post(
            "/snapshots",
            json={
                "publication_id": publication.id,
                "views": 25,
                "watch_time_seconds": 900,
                "likes": 5,
                "comments": 2,
                "shares": 9,
                "captured_at": "2026-11-02T00:00:00Z",
            },
        )
        assert second.status_code == 200

        history = client.get(f"/publications/{publication.id}/snapshots")
    assert history.status_code == 200
    rows = history.json()
    assert [row["captured_at"] for row in rows] == ["2026-11-02T00:00:00Z", "2026-11-01T00:00:00Z"]
    assert rows[0]["views"] == 25
    assert rows[0]["watch_time_seconds"] == 900
    assert rows[0]["likes"] == 5
    assert rows[0]["comments"] == 2
    assert rows[0]["shares"] == 9


def test_a_backdated_snapshot_lands_where_its_captured_at_says(tmp_path):
    """US-030: history follows captured_at, not the insert order, so a
    snapshot POSTed later with an earlier timestamp reads back earlier."""
    store = open_store(tmp_path)
    publication = _publication(store)
    with TestClient(create_app(store)) as client:
        later = client.post(
            "/snapshots",
            json={"publication_id": publication.id, "views": 25, "captured_at": "2026-11-02T00:00:00Z"},
        )
        assert later.status_code == 200
        backdated = client.post(
            "/snapshots",
            json={"publication_id": publication.id, "views": 10, "captured_at": "2026-11-01T00:00:00Z"},
        )
        assert backdated.status_code == 200
        history = client.get(f"/publications/{publication.id}/snapshots")
        results = client.get("/results")
    assert history.status_code == 200
    rows = history.json()
    assert [row["captured_at"] for row in rows] == ["2026-11-02T00:00:00Z", "2026-11-01T00:00:00Z"]
    assert rows[0]["views"] == 25
    assert [row["captured_at"] for row in store.list_snapshots(publication.id)] == [
        "2026-11-01T00:00:00Z",
        "2026-11-02T00:00:00Z",
    ]
    # The latest snapshot by captured_at is the one /results reports.
    assert results.json()[0]["views"] == 25


def test_snapshot_history_for_an_unknown_publication_is_404(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        response = client.get("/publications/pub-missing/snapshots")
    assert response.status_code == 404


def test_a_snapshot_with_an_unparseable_captured_at_is_refused(tmp_path):
    """Snapshots order by captured_at (US-030): a value the clock cannot
    read would corrupt the history's order, so it never lands."""
    store = open_store(tmp_path)
    publication = _publication(store)
    with TestClient(create_app(store)) as client:
        response = client.post(
            "/snapshots",
            json={"publication_id": publication.id, "views": 5, "captured_at": "yesterday"},
        )
    assert response.status_code == 422
    assert response.json()["detail"] == "captured_at must be an ISO timestamp"
    assert store.list_snapshots(publication.id) == []


def test_snapshot_history_is_empty_before_any_recording(tmp_path):
    store = open_store(tmp_path)
    publication = _publication(store)
    with TestClient(create_app(store)) as client:
        response = client.get(f"/publications/{publication.id}/snapshots")
    assert response.status_code == 200
    assert response.json() == []


def test_a_blank_count_is_stored_absent_not_zero(tmp_path):
    """US-038: only the counts the operator measured are stored. A blank on
    the wire is absent (null) end to end, and an explicit 0 stays a
    measured zero."""
    store = open_store(tmp_path)
    publication = _publication(store)
    with TestClient(create_app(store)) as client:
        first = client.post(
            "/snapshots",
            json={"publication_id": publication.id, "views": 12, "captured_at": "2026-11-02T00:00:00Z"},
        )
        assert first.status_code == 200
        second = client.post(
            "/snapshots",
            json={
                "publication_id": publication.id,
                "views": 0,
                "likes": 3,
                "captured_at": "2026-11-03T00:00:00Z",
            },
        )
        assert second.status_code == 200
        history = client.get(f"/publications/{publication.id}/snapshots").json()
    assert history[0]["captured_at"] == "2026-11-03T00:00:00Z"
    assert history[0]["views"] == 0
    assert history[0]["likes"] == 3
    assert history[0]["watch_time_seconds"] is None
    assert history[0]["comments"] is None
    assert history[0]["shares"] is None
    assert history[1]["views"] == 12
    assert history[1]["likes"] is None
    stored = store.list_snapshots(publication.id)
    # The store-level readback is oldest-first: the backdated 0-views row,
    # then the first one.
    assert stored[0]["views"] == 12
    assert stored[0]["watch_time_seconds"] is None
    assert stored[1]["views"] == 0
    assert stored[1]["watch_time_seconds"] is None


def test_results_do_not_count_views_the_latest_snapshot_left_absent(tmp_path):
    """US-038: an absent views count is "not measured"; the results total
    skips it instead of reading it as a measured zero."""
    store = open_store(tmp_path)
    publication = _publication(store)
    with TestClient(create_app(store)) as client:
        assert (
            client.post(
                "/snapshots",
                json={"publication_id": publication.id, "views": 40, "captured_at": "2026-11-01T00:00:00Z"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/snapshots",
                json={"publication_id": publication.id, "likes": 2},
            ).status_code
            == 200
        )
        rows = client.get("/results").json()
    assert rows[0]["views"] == 0
