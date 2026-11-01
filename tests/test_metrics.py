from fastapi.testclient import TestClient

from deadinternet.api import create_app
from deadinternet.metrics.pull import record_snapshot
from tests.helpers import open_store


def test_failed_snapshot_does_not_add_a_row(tmp_path):
    store = open_store(tmp_path)
    failed = {
        "failed": True,
        "views": 0,
        "watch_time_seconds": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
    }
    record_snapshot(store, "pub-1", failed)
    assert store.list_snapshots("pub-1") == []

    record_snapshot(
        store,
        "pub-1",
        {
            "views": 10,
            "watch_time_seconds": 4,
            "likes": 1,
            "comments": 0,
            "shares": 0,
            "captured_at": "2026-10-31T00:00:00Z",
        },
    )
    assert store.list_snapshots("pub-1") == [
        {
            "publication_id": "pub-1",
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
            json={"publication_id": "pub-1", "views": 0, "failed": True},
        )
    assert response.status_code == 200
    assert len(store.list_snapshots("pub-1")) == 1
