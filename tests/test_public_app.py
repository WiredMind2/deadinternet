import re
from pathlib import Path

from fastapi.testclient import TestClient

from deadinternet.api import create_app
from deadinternet.domain.experiment import Affiliate
from deadinternet.public_app import create_public_app
from tests.helpers import experiment, open_store


def _concrete(path: str) -> str:
    """A requestable stand-in for a templated admin path."""
    return re.sub(r"\{[^}]+\}", "stub", path)


def test_the_public_app_has_exactly_one_route(tmp_path):
    app = create_public_app(open_store(tmp_path))
    routes = [
        (route.path, sorted(route.methods - {"HEAD", "OPTIONS"}))
        for route in app.routes
    ]
    assert routes == [("/r/{code}", ["GET"])]


def test_every_admin_route_returns_404_on_the_public_app(tmp_path):
    """US-034: the public app serves clicks, not the lab's write surface.

    Driven off the admin app's own route table, so an admin route added
    later is automatically asserted to stay absent here.
    """
    store = open_store(tmp_path)
    admin = create_app(store)
    public = create_public_app(store)
    with TestClient(public) as client:
        for route in admin.routes:
            if route.path == "/r/{code}":
                # The one route both apps share by design.
                continue
            path = _concrete(route.path)
            methods = getattr(route, "methods", None) or {"GET"}
            for method in sorted(methods - {"HEAD", "OPTIONS"}):
                response = client.request(method, path)
                assert response.status_code == 404, f"{method} {path} is exposed"


def test_a_public_click_is_logged_exactly_like_an_admin_click(tmp_path):
    """Both apps funnel through hit(), so one shared counter and click log."""
    store = open_store(tmp_path)
    store.upsert_offer("acme", "Acme", "https://acme.test/deal", merchant="acme")
    store.insert_experiment(
        experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme"))
    )
    with TestClient(create_app(store)) as admin, TestClient(create_public_app(store)) as public:
        via_public = public.get("/r/code-a", follow_redirects=False)
        via_admin = admin.get("/r/code-a", follow_redirects=False)
    assert via_public.status_code == 302
    assert via_admin.status_code == 302
    assert via_public.headers["location"] == "https://acme.test/deal"
    assert via_admin.headers["location"] == "https://acme.test/deal"
    assert store.get_experiment("exp-a").clicks == 2
    assert len(store.list_click_times("exp-a")) == 2


def test_an_unknown_code_is_a_404_without_store_details(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-a"))
    with TestClient(create_public_app(store)) as client:
        response = client.get("/r/missing", follow_redirects=False)
    assert response.status_code == 404
    assert response.json()["detail"] == "unknown tracking code"
    assert store.get_experiment("exp-a").clicks == 0
    assert store.list_click_times("exp-a") == []


def test_an_unconfigured_merchant_is_a_404_without_naming_it(tmp_path):
    """The admin app names the merchant and its POST /offers fix in the
    detail; the public app mirrors the 404 and the no-click effect while
    deliberately saying nothing about the store."""
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme"))
    )
    with TestClient(create_app(store)) as admin, TestClient(create_public_app(store)) as public:
        via_admin = admin.get("/r/code-a", follow_redirects=False)
        via_public = public.get("/r/code-a", follow_redirects=False)
    assert via_admin.status_code == 404
    assert "acme" in via_admin.json()["detail"]
    assert via_public.status_code == 404
    assert via_public.json()["detail"] == "unknown tracking code"
    assert store.get_experiment("exp-a").clicks == 0
    assert store.list_click_times("exp-a") == []


def test_main_public_serves_the_click_app_on_its_own_port(monkeypatch, tmp_path):
    seen = {}

    def fake_create_public_app(store):
        seen["store"] = store
        return "public-app"

    def fake_run(app, host, port):
        seen["app"] = app
        seen["host"] = host
        seen["port"] = port

    monkeypatch.setattr("deadinternet.__main__.create_public_app", fake_create_public_app)
    monkeypatch.setattr("deadinternet.__main__.uvicorn.run", fake_run)
    monkeypatch.setattr("deadinternet.__main__.Store", lambda path: path)
    monkeypatch.delenv("DEADINTERNET_PUBLIC_PORT", raising=False)
    monkeypatch.delenv("DEADINTERNET_PUBLIC_HOST", raising=False)
    monkeypatch.chdir(tmp_path)

    from deadinternet.__main__ import main_public

    main_public()
    assert seen["app"] == "public-app"
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 8001
    repo_db = Path(__file__).resolve().parents[1] / "data" / "deadinternet.sqlite"
    assert seen["store"] == str(repo_db)


def test_the_public_port_comes_from_the_argument_then_the_env(monkeypatch, tmp_path):
    seen = {}

    def fake_run(app, host, port):
        seen["port"] = port

    monkeypatch.setattr("deadinternet.__main__.create_public_app", lambda store: "app")
    monkeypatch.setattr("deadinternet.__main__.uvicorn.run", fake_run)
    monkeypatch.setattr("deadinternet.__main__.Store", lambda path: path)
    monkeypatch.delenv("DEADINTERNET_PUBLIC_PORT", raising=False)
    monkeypatch.chdir(tmp_path)

    from deadinternet.__main__ import main_public

    main_public(port=9001)
    assert seen["port"] == 9001
    monkeypatch.setenv("DEADINTERNET_PUBLIC_PORT", "9002")
    main_public()
    assert seen["port"] == 9002
    # An explicit port beats the environment.
    main_public(port=9003)
    assert seen["port"] == 9003


def test_dispatch_serves_the_admin_by_default_and_the_click_app_on_public(monkeypatch):
    calls = []
    monkeypatch.setattr("deadinternet.__main__.main", lambda: calls.append(("admin", None)))
    monkeypatch.setattr(
        "deadinternet.__main__.main_public",
        lambda port=None: calls.append(("public", port)),
    )

    from deadinternet.__main__ import _dispatch

    _dispatch([])
    assert calls == [("admin", None)]
    _dispatch(["--public"])
    assert calls[-1] == ("public", None)
    _dispatch(["--public", "9101"])
    assert calls[-1] == ("public", 9101)
