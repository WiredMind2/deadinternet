"""LangChain proposer. It returns one draft and does not persist or render."""

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from deadinternet.domain.experiment import (
    Affiliate,
    Experiment,
    FacelessStyle,
    OwnOffer,
    PlatformPayout,
    Status,
    Style,
)
from deadinternet.domain.proposal import Catalog, DraftSpec, ProposalRejected, parse_proposal
from deadinternet.propose.lint import draft_problems

MAX_STEPS = 12
DEFAULT_BASE_URL = "https://llm.tetrazero.com/v1"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SYSTEM_PROMPT = """
You propose the next short vertical video experiment for this lab.
Pick the parent with the highest revenue_cents, then clicks, then id.
Change a real factor. Use only ids from get_catalog.
Read the parent script before you write. The new script must not be a near-copy.
A near-copy is the same script and the same look.
Call validate_draft before submit_draft. Repair any rejection, then submit once.
A rejection may name the hook score, the caption fold, or stock phrases. Fix what it names.
Submit exactly one draft.
A TikTok Creator Rewards video must be longer than 60 seconds.
Do not render or post.
""".strip()


class ProposerUnavailable(Exception):
    pass


class ProposerFailed(Exception):
    pass


@dataclass
class ProposeRun:
    experiments: tuple[Experiment, ...]
    catalog: Catalog
    submitted: DraftSpec | None = None


class DraftArgs(BaseModel):
    parent_ids: list[str] = Field(default_factory=list)
    factor_diffs: list[dict[str, str]] = Field(default_factory=list)
    niche_id: str
    style: dict
    money: dict
    hook_id: str
    hypothesis: str
    script: str
    caption: str
    length_sec: int


def model_is_diverted(model: str) -> bool:
    name = model.rsplit("/", 1)[-1].strip().lower()
    return name.startswith("claude") or name.startswith("gemini")


def chat_from_env(environ: Mapping[str, str] | None = None, client_builder: Callable | None = None):
    env = os.environ if environ is None else environ
    key = env.get("DEADINTERNET_LLM_API_KEY", "").strip()
    model = env.get("DEADINTERNET_LLM_MODEL", "").strip()
    if not key or not model:
        raise ProposerUnavailable("DEADINTERNET_LLM_API_KEY and DEADINTERNET_LLM_MODEL are required")
    if model_is_diverted(model):
        raise ProposerUnavailable("model is routed away from tool calls")
    headers = {"User-Agent": USER_AGENT}
    access_id = env.get("CF_ACCESS_CLIENT_ID", "").strip()
    access_secret = env.get("CF_ACCESS_CLIENT_SECRET", "").strip()
    if access_id and access_secret:
        headers["CF-Access-Client-Id"] = access_id
        headers["CF-Access-Client-Secret"] = access_secret
    base_url = env.get("DEADINTERNET_LLM_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    builder = client_builder or _build_chat
    return builder(
        model=model,
        api_key=key,
        base_url=base_url,
        default_headers=headers,
        timeout=60,
    )


def _build_chat(**kwargs):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(**kwargs)


def _default_agent(model, tools, prompt: str):
    from langchain.agents import create_agent

    return create_agent(model=model, tools=tools, system_prompt=prompt)


def run_agent(model, tools, prompt: str, run: ProposeRun, agent_factory: Callable | None = None) -> None:
    try:
        factory = agent_factory or _default_agent
        agent = factory(model, tools, prompt)
        agent.invoke(
            {"messages": [{"role": "user", "content": "Propose the next experiment."}]},
            config={"recursion_limit": MAX_STEPS},
        )
    except (ProposerFailed, AssertionError):
        raise
    except Exception:
        if run.submitted is None:
            raise ProposerFailed("model call failed") from None


class RepairProposer:
    def __init__(
        self,
        model=None,
        runner: Callable | None = None,
        environ: Mapping[str, str] | None = None,
        client_builder: Callable | None = None,
        agent_factory: Callable | None = None,
    ):
        self._model = model
        self._runner = runner
        self._environ = environ
        self._client_builder = client_builder
        self._agent_factory = agent_factory

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "RepairProposer":
        return cls(environ=environ)

    def propose(self, experiments: list[Experiment], catalog: Catalog) -> list[DraftSpec]:
        if not any(row.status is Status.complete for row in experiments):
            return []
        run = ProposeRun(experiments=tuple(experiments), catalog=catalog)
        tools = make_tools(run)
        try:
            if self._runner is not None:
                self._runner(self._model, tools, SYSTEM_PROMPT, run)
            else:
                model = self._model
                if model is None:
                    model = chat_from_env(self._environ, self._client_builder)
                run_agent(model, tools, SYSTEM_PROMPT, run, agent_factory=self._agent_factory)
        except (ProposerUnavailable, ProposerFailed, AssertionError):
            raise
        except Exception:
            raise ProposerFailed("model call failed") from None
        if run.submitted is None:
            raise ProposerFailed("no draft submitted")
        return [run.submitted]


def make_tools(run: ProposeRun):
    @tool
    def list_finished() -> str:
        """List completed experiments. Scores are revenue_cents, then clicks, then id. Scripts are omitted."""
        rows = [row for row in run.experiments if row.status is Status.complete]
        rows.sort(key=lambda row: (row.revenue_cents, row.clicks, row.id), reverse=True)
        payload = [
            {
                "id": row.id,
                "niche_id": row.niche_id,
                "hook_id": row.hook_id,
                "style_kind": row.style.kind,
                "money_kind": row.money.kind,
                "revenue_cents": row.revenue_cents,
                "clicks": row.clicks,
                "length_sec": row.length_sec,
                "hypothesis": row.hypothesis,
            }
            for row in rows
        ]
        return json.dumps(payload)

    @tool
    def get_catalog() -> str:
        """Return the allowed niche, presenter, voice, hook, and offer ids."""
        catalog = run.catalog
        payload = {
            "niche_ids": sorted(catalog.niche_ids),
            "presenter_ids": sorted(catalog.presenter_ids),
            "voice_ids": sorted(catalog.voice_ids),
            "hook_ids": sorted(catalog.hook_ids),
            "offer_ids": sorted(catalog.offer_ids),
        }
        return json.dumps(payload)

    @tool
    def read_parent(experiment_id: str) -> str:
        """Return one experiment, including its script, caption, style, and money path."""
        parent = run.catalog.parents.get(experiment_id)
        if parent is None:
            return f"unknown parent {experiment_id}"
        payload = {
            "id": parent.id,
            "niche_id": parent.niche_id,
            "hook_id": parent.hook_id,
            "hypothesis": parent.hypothesis,
            "script": parent.script,
            "caption": parent.caption,
            "length_sec": parent.length_sec,
            "revenue_cents": parent.revenue_cents,
            "clicks": parent.clicks,
            "style": _style_dict(parent.style),
            "money": _money_dict(parent.money),
        }
        return json.dumps(payload)

    @tool(args_schema=DraftArgs)
    def validate_draft(
        parent_ids: list[str],
        factor_diffs: list[dict[str, str]],
        niche_id: str,
        style: dict,
        money: dict,
        hook_id: str,
        hypothesis: str,
        script: str,
        caption: str,
        length_sec: int,
    ) -> str:
        """Check one draft against the catalog. Returns ok or the rejection. Does not submit."""
        _draft, message = _evaluate(
            run,
            _raw_draft(
                parent_ids,
                factor_diffs,
                niche_id,
                style,
                money,
                hook_id,
                hypothesis,
                script,
                caption,
                length_sec,
            ),
        )
        return message

    @tool(args_schema=DraftArgs)
    def submit_draft(
        parent_ids: list[str],
        factor_diffs: list[dict[str, str]],
        niche_id: str,
        style: dict,
        money: dict,
        hook_id: str,
        hypothesis: str,
        script: str,
        caption: str,
        length_sec: int,
    ) -> str:
        """Submit one accepted draft. A rejection is returned so you can repair it. The first success sticks."""
        if run.submitted is not None:
            return "already submitted"
        draft, message = _evaluate(
            run,
            _raw_draft(
                parent_ids,
                factor_diffs,
                niche_id,
                style,
                money,
                hook_id,
                hypothesis,
                script,
                caption,
                length_sec,
            ),
        )
        if draft is None:
            return message
        run.submitted = draft
        return "submitted"

    return [list_finished, get_catalog, read_parent, validate_draft, submit_draft]


def _raw_draft(
    parent_ids,
    factor_diffs,
    niche_id,
    style,
    money,
    hook_id,
    hypothesis,
    script,
    caption,
    length_sec,
) -> dict:
    return {
        "parent_ids": list(parent_ids),
        "factor_diffs": list(factor_diffs),
        "niche_id": niche_id,
        "style": style,
        "money": money,
        "hook_id": hook_id,
        "hypothesis": hypothesis,
        "script": script,
        "caption": caption,
        "length_sec": length_sec,
    }


def _evaluate(run: ProposeRun, raw: dict) -> tuple[DraftSpec | None, str]:
    try:
        draft = parse_proposal([raw], run.catalog)[0]
    except (ProposalRejected, KeyError, ValueError, TypeError) as exc:
        return None, str(exc)
    problems = draft_problems(draft)
    if problems:
        return None, " ".join(problems)
    return draft, "ok"


def _style_dict(style: Style) -> dict:
    if isinstance(style, FacelessStyle):
        return {
            "kind": "faceless",
            "look": style.look.value,
            "voice_id": style.voice_id,
            "caption_style": style.caption_style,
        }
    return {
        "kind": "avatar",
        "presenter_id": style.presenter_id,
        "voice_id": style.voice_id,
    }


def _money_dict(money) -> dict:
    if isinstance(money, Affiliate):
        return {
            "kind": "affiliate",
            "tracking_code": money.tracking_code,
            "merchant": money.merchant,
        }
    if isinstance(money, OwnOffer):
        return {
            "kind": "own_offer",
            "tracking_code": money.tracking_code,
            "offer_url": money.offer_url,
        }
    if isinstance(money, PlatformPayout):
        return {"kind": "platform_payout", "platform": money.platform.value}
    raise TypeError(f"unknown money path {money!r}")
