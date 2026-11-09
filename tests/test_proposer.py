import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deadinternet.api.app import create_app
from deadinternet.domain.experiment import AvatarStyle, OwnOffer, Platform, PlatformPayout, Status
from deadinternet.domain.proposal import Catalog
from deadinternet.propose.agent import (
    MAX_STEPS,
    SYSTEM_PROMPT,
    ProposerFailed,
    ProposerUnavailable,
    ProposeRun,
    RepairProposer,
    _default_agent,
    chat_from_env,
    make_tools,
)
from tests.helpers import experiment, open_store


def _catalog(**overrides) -> Catalog:
    base = dict(
        niche_ids=frozenset({"niche-1"}),
        presenter_ids=frozenset({"presenter-1"}),
        voice_ids=frozenset({"voice-1"}),
        offer_ids=frozenset({"acme", "https://shop.example/offer"}),
        hook_ids=frozenset({"question", "result"}),
        parents={},
    )
    base.update(overrides)
    return Catalog(**base)


def _draft(**overrides) -> dict:
    body = {
        "parent_ids": [],
        "factor_diffs": [{"field": "hook_id", "parent_value": "question", "next_value": "result"}],
        "niche_id": "niche-1",
        "style": {
            "kind": "faceless",
            "look": "stills",
            "voice_id": "voice-1",
            "caption_style": "bold",
        },
        "money": {"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"},
        "hook_id": "result",
        "hypothesis": "A result hook beats the question hook.",
        "script": "I lost $18,000 on one missing contract.",
        "caption": "That contract cost me $18,000.",
        "length_sec": 75,
    }
    body.update(overrides)
    return body


def _tools(tools):
    return {item.name: item for item in tools}


def _seed(tmp_path):
    store = open_store(tmp_path)
    store.upsert_theme("history", "History")
    store.upsert_niche("niche-1", "history", "Niche")
    store.upsert_presenter("presenter-1", "Alex", "heygen")
    store.upsert_voice("voice-1", "Nova", "eleven")
    store.upsert_hook("question", "Question")
    store.upsert_hook("result", "Result")
    store.upsert_offer("acme", "Acme", "https://example.test/acme", merchant="acme")
    store.insert_experiment(
        experiment(
            id="exp-parent",
            status=Status.complete,
            revenue_cents=500,
            clicks=4,
        )
    )
    return store


def test_no_completed_experiment_skips_the_runner():
    def runner(*_args):
        raise AssertionError("runner called")

    proposer = RepairProposer(runner=runner)
    catalog = _catalog()
    assert proposer.propose([], catalog) == []
    assert proposer.propose([experiment(status=Status.live)], catalog) == []


def test_repair_then_submit_keeps_the_first_draft():
    parent = experiment(id="exp-parent", status=Status.complete, revenue_cents=500, clicks=4)
    catalog = _catalog(parents={parent.id: parent})
    seen = {}

    def runner(_model, tools, prompt, _run):
        assert "validate_draft" in prompt
        by_name = _tools(tools)
        seen["rejected"] = by_name["validate_draft"].invoke(_draft(niche_id="missing-niche"))
        seen["submitted"] = by_name["submit_draft"].invoke(
            _draft(parent_ids=[parent.id], script="I lost $18,000 on one missing contract.")
        )
        seen["second"] = by_name["submit_draft"].invoke(
            _draft(parent_ids=[parent.id], script="A later script that must not replace the first.")
        )

    drafts = RepairProposer(runner=runner, model=object()).propose([parent], catalog)
    assert "unknown niche" in seen["rejected"]
    assert seen["submitted"] == "submitted"
    assert seen["second"] == "already submitted"
    assert drafts[0].script == "I lost $18,000 on one missing contract."
    assert drafts[0].hook_id == "result"


def test_lint_rejection_is_repaired_then_accepted():
    parent = experiment(id="exp-parent", status=Status.complete)
    catalog = _catalog(parents={parent.id: parent})
    seen = {}

    def runner(_model, tools, _prompt, _run):
        by_name = _tools(tools)
        seen["rejected"] = by_name["submit_draft"].invoke(
            _draft(parent_ids=[parent.id], script="Here is how the story goes.")
        )
        seen["repaired"] = by_name["submit_draft"].invoke(
            _draft(parent_ids=[parent.id])
        )

    drafts = RepairProposer(runner=runner, model=object()).propose([parent], catalog)
    assert "hook scores" in seen["rejected"]
    assert "rewrite the first spoken beat" in seen["rejected"]
    assert seen["repaired"] == "submitted"
    assert drafts[0].script == "I lost $18,000 on one missing contract."


def test_near_copy_submit_is_not_stored():
    parent = experiment(id="exp-parent", status=Status.complete)
    catalog = _catalog(parents={parent.id: parent})
    seen = {}

    def runner(_model, tools, _prompt, _run):
        seen["message"] = _tools(tools)["submit_draft"].invoke(
            _draft(parent_ids=[parent.id], script=parent.script, hook_id=parent.hook_id)
        )

    proposer = RepairProposer(runner=runner, model=object())
    with pytest.raises(ProposerFailed, match="no draft submitted"):
        proposer.propose([parent], catalog)
    assert "near-copy" in seen["message"]


def test_route_returns_the_repaired_draft_without_writing(tmp_path):
    store = _seed(tmp_path)

    def runner(_model, tools, _prompt, _run):
        by_name = _tools(tools)
        finished = json.loads(by_name["list_finished"].invoke({}))
        parent_id = finished[0]["id"]
        assert "unknown niche" in by_name["validate_draft"].invoke(_draft(niche_id="missing-niche"))
        by_name["submit_draft"].invoke(
            _draft(parent_ids=[parent_id], script="I cut my $140 phone bill to $9 in one call.")
        )

    proposer = RepairProposer(runner=runner, model=object())
    with TestClient(create_app(store, proposer=proposer)) as client:
        response = client.post("/suggest")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["script"] == "I cut my $140 phone bill to $9 in one call."
    assert body[0]["niche_id"] == "niche-1"
    assert [row.id for row in store.list_experiments()] == ["exp-parent"]
    assert list(tmp_path.rglob("*.mp4")) == []


def test_route_returns_502_when_nothing_is_submitted(tmp_path):
    store = _seed(tmp_path)

    def runner(_model, _tools, _prompt, _run):
        return None

    proposer = RepairProposer(runner=runner, model=object())
    with TestClient(create_app(store, proposer=proposer)) as client:
        response = client.post("/suggest")
    assert response.status_code == 502
    assert response.json()["detail"] == "no draft submitted"
    assert [row.id for row in store.list_experiments()] == ["exp-parent"]


def test_missing_key_is_503_and_builds_no_client(tmp_path):
    store = _seed(tmp_path)
    built = []
    proposer = RepairProposer(
        environ={},
        client_builder=lambda **kwargs: built.append(kwargs),
    )
    with TestClient(create_app(store, proposer=proposer)) as client:
        response = client.post("/suggest")
    assert response.status_code == 503
    assert "DEADINTERNET_LLM_API_KEY" in response.json()["detail"]
    assert built == []
    assert "proxy-key" not in response.text


@pytest.mark.parametrize(
    "model_name",
    ["claude-sonnet", "anthropic/claude-opus", "gemini-2.5-pro", "google/gemini-flash"],
)
def test_diverted_model_does_not_build_a_client(model_name):
    built = []
    parent = experiment(status=Status.complete)
    proposer = RepairProposer(
        environ={
            "DEADINTERNET_LLM_API_KEY": "proxy-key",
            "DEADINTERNET_LLM_MODEL": model_name,
        },
        client_builder=lambda **kwargs: built.append(kwargs),
    )
    with pytest.raises(ProposerUnavailable, match="routed away"):
        proposer.propose([parent], _catalog(parents={parent.id: parent}))
    assert built == []


def test_chat_client_uses_the_proxy_and_access_headers():
    seen = {}

    def builder(**kwargs):
        seen.update(kwargs)
        return object()

    chat_from_env(
        {
            "DEADINTERNET_LLM_API_KEY": "proxy-key",
            "DEADINTERNET_LLM_MODEL": "grok-4",
            "DEADINTERNET_LLM_BASE_URL": "https://llm.tetrazero.com/v1",
            "CF_ACCESS_CLIENT_ID": "access-id",
            "CF_ACCESS_CLIENT_SECRET": "access-secret",
        },
        builder,
    )
    assert seen["model"] == "grok-4"
    assert seen["base_url"] == "https://llm.tetrazero.com/v1"
    assert seen["api_key"] == "proxy-key"
    assert seen["default_headers"]["User-Agent"].startswith("Mozilla/5.0")
    assert seen["default_headers"]["CF-Access-Client-Id"] == "access-id"
    assert seen["default_headers"]["CF-Access-Client-Secret"] == "access-secret"
    assert "proxy-key" not in seen["default_headers"].values()


def test_access_headers_require_both_values():
    seen = {}
    chat_from_env(
        {
            "DEADINTERNET_LLM_API_KEY": "proxy-key",
            "DEADINTERNET_LLM_MODEL": "grok-4",
            "CF_ACCESS_CLIENT_ID": "access-id",
        },
        lambda **kwargs: seen.update(kwargs),
    )
    assert "CF-Access-Client-Id" not in seen["default_headers"]


def test_graph_error_after_submit_still_returns_the_draft():
    parent = experiment(id="exp-parent", status=Status.complete)
    catalog = _catalog(parents={parent.id: parent})
    good = _draft(parent_ids=[parent.id], script="The second cut saved me 40 bucks a month.")

    def factory(_model, tools, prompt):
        assert prompt == SYSTEM_PROMPT

        class Agent:
            def invoke(self, _payload, config):
                assert config == {"recursion_limit": MAX_STEPS}
                _tools(tools)["submit_draft"].invoke(good)
                raise RuntimeError("step cap")

        return Agent()

    drafts = RepairProposer(model=object(), agent_factory=factory).propose([parent], catalog)
    assert drafts[0].script == "The second cut saved me 40 bucks a month."


def test_graph_error_before_submit_fails_closed():
    parent = experiment(status=Status.complete)

    def factory(_model, _tools, _prompt):
        class Agent:
            def invoke(self, _payload, _config):
                raise RuntimeError("upstream")

        return Agent()

    proposer = RepairProposer(model=object(), agent_factory=factory)
    with pytest.raises(ProposerFailed, match="model call failed"):
        proposer.propose([parent], _catalog(parents={parent.id: parent}))


def test_parent_views_include_avatar_and_each_money_path():
    affiliate = experiment(id="aff", status=Status.complete, revenue_cents=10, clicks=1)
    payout = experiment(
        id="pay",
        status=Status.complete,
        revenue_cents=50,
        clicks=2,
        style=AvatarStyle(presenter_id="presenter-1", voice_id="voice-1"),
        money=PlatformPayout(platform=Platform.youtube),
    )
    own = experiment(
        id="own",
        status=Status.complete,
        revenue_cents=20,
        clicks=3,
        money=OwnOffer(tracking_code="own", offer_url="https://shop.example/offer"),
    )
    catalog = _catalog(parents={row.id: row for row in (affiliate, payout, own)})
    tools = _tools(make_tools(ProposeRun(experiments=(affiliate, payout, own), catalog=catalog)))
    finished = json.loads(tools["list_finished"].invoke({}))
    assert [row["id"] for row in finished] == ["pay", "own", "aff"]
    affiliate_view = json.loads(tools["read_parent"].invoke({"experiment_id": "aff"}))
    assert affiliate_view["money"]["merchant"] == "acme"
    avatar = json.loads(tools["read_parent"].invoke({"experiment_id": "pay"}))
    assert avatar["style"]["kind"] == "avatar"
    assert avatar["money"]["platform"] == "youtube"
    owned = json.loads(tools["read_parent"].invoke({"experiment_id": "own"}))
    assert owned["money"]["kind"] == "own_offer"
    assert "unknown parent" in tools["read_parent"].invoke({"experiment_id": "missing"})
    catalog_ids = json.loads(tools["get_catalog"].invoke({}))
    assert catalog_ids["niche_ids"] == ["niche-1"]


def test_default_client_and_agent_construct_without_a_request():
    model = chat_from_env(
        {
            "DEADINTERNET_LLM_API_KEY": "proxy-key",
            "DEADINTERNET_LLM_MODEL": "grok-4",
        }
    )
    assert type(model).__name__ == "ChatOpenAI"
    parent = experiment(status=Status.complete)
    run = ProposeRun(experiments=(parent,), catalog=_catalog(parents={parent.id: parent}))
    agent = _default_agent(model, make_tools(run), SYSTEM_PROMPT)
    assert callable(agent.invoke)


def test_propose_module_does_not_import_render_or_publish():
    path = Path(__file__).parents[1] / "src" / "deadinternet" / "propose" / "agent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    assert all(not name.startswith("deadinternet.render") for name in modules)
    assert all(not name.startswith("deadinternet.publish") for name in modules)
