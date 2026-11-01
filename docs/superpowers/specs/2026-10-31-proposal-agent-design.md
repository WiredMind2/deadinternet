# Proposal repair agent

The lab already decides status, money, and approval in code. `POST /suggest` returns one draft and saves nothing. The dashboard shows that draft and only creates an experiment when a person presses Accept. The gap is the writer. `suggest()` in `src/deadinternet/domain/rank.py` still fills hypothesis, script, and caption with placeholders.

A LangChain agent is used only by the live app. It reads finished experiments and the catalog, submits one draft, and can repair that draft when `parse_proposal` rejects it. Render and posting stay where they are.

## Operator outcome

Pressing Suggest still calls `POST /suggest`. With at least one completed experiment, the response is one draft in the same JSON shape as `_draft_json`. Accept drafts still posts that JSON to `POST /experiments`. No completed experiment still returns an empty list and does not call the model. A missing key, a diverted model name, or a loop that never submits a valid draft leaves the database unchanged and returns an error the existing banner already shows.

## Model client

`llm.tetrazero.com` is the GrokServer proxy. Chat is `POST /v1/chat/completions` with `Authorization: Bearer`. The proxy key stays on the server. This app reads it from the environment and never writes it into the repo or a log line.

- `DEADINTERNET_LLM_BASE_URL` defaults to `https://llm.tetrazero.com/v1`.
- `DEADINTERNET_LLM_API_KEY` is the proxy bearer key.
- `DEADINTERNET_LLM_MODEL` is required. A name the proxy would send to Claude or Gemini is a configuration error. Claude is any id whose last path segment starts with `claude`. That translator has no tool field. Gemini uses the same prefix rule as `is_gemini_model` in the proxy. Other ids are forwarded to xAI, which is what tool calls need.
- When `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` are both set, send them on every request. Also send a normal browser User-Agent.

Use `ChatOpenAI` from `langchain-openai` with that base URL, key, model, and headers. Build the client on the first suggest call so the API can boot without the key. A missing key or a diverted model becomes HTTP 503. An upstream failure, timeout, or unfinished loop becomes HTTP 502. The detail string does not include the key or the Access secrets.

Dependencies are `langchain` and `langchain-openai` in `pyproject.toml`. The agent constructor is the current tool-calling helper those packages export (`langchain.agents.create_agent` on the 1.x line). The legacy `AgentExecutor` is not used.

## Agent

Module `src/deadinternet/propose/agent.py`. One type, `RepairProposer`, with `propose(experiments, catalog) -> list[DraftSpec]`.

Data closed over for a single call is a run object. Tools read that object. They do not touch SQLite, the renderer, or the publisher.

Tools:

- `list_finished` returns completed rows only. Fields are id, niche, hook, style kind, money kind, revenue cents, clicks, length, and hypothesis. No script.
- `get_catalog` returns the id sets from `Catalog`. Niche, presenter, voice, hook, and offer ids.
- `read_parent` returns one experiment, including script, caption, style, and money, so the model can avoid a near-copy.
- `validate_draft` runs `parse_proposal` on one raw draft. Success returns a short ok. Failure returns the `ProposalRejected` message and does not finish the run.
- `submit_draft` runs the same check. Success stores that one `DraftSpec` on the run and tells the model to stop. Failure returns the error so the model can repair and submit again. A second success does not replace the first.

The system prompt is a constant in that module. Revenue cents, then clicks, then id pick the parent worth varying. The model must use catalog ids only, change a real factor, keep the script off a near-copy of a parent, call `validate_draft` before `submit_draft`, and submit once. A TikTok Creator Rewards draft has to be longer than 60 seconds, because `approve` rejects a shorter one later.

The graph is capped at 12 steps. If a draft was submitted, return a one-item list. If not, raise a failure the route maps to 502.

`suggest()` in the domain stays. Tests that call it directly keep covering the placeholder rules. `propose()` is a separate path.

## HTTP wiring

`create_app` gains an optional `proposer`. When it is omitted, `POST /suggest` keeps calling `suggest()`, so the existing API tests stay offline. When it is set, the route calls `proposer.propose` and serializes with `_draft_json`.

`python -m deadinternet` always passes `RepairProposer.from_env()`. The server still starts if the key is missing. Only Suggest fails, with 503.

The Suggest sentence in `web/src/App.jsx` says the model writes the next draft from completed videos. The rest of the panel already shows factor diffs, hypothesis, script, and caption.

## Tests

`tests/test_proposer.py` does not call `llm.tetrazero.com`. A scripted runner invokes the tools.

- No completed experiment returns an empty list and the runner is not called.
- A first `validate_draft` fails on an unknown niche, then `submit_draft` succeeds. The returned draft is the repaired one. The store is unchanged and no mp4 appears.
- A near-copy submit returns the rejection and does not count as submitted.
- The runner stops without a successful submit. The route returns 502.
- A model id starting with `claude` fails before any HTTP client is built.
- `create_app` with an injected proposer returns that draft from `POST /suggest` and inserts nothing.
- The propose module does not import the render or publish packages.

Coverage on `deadinternet` stays at 85% or higher. Existing suggest tests stay on the deterministic function.

## Out of scope

No change to render, publish, approval, or the starter grid. No fallback to the placeholder writer when the model is down. No batch of drafts. No Claude or Gemini tool calling until that proxy translates tool fields. The proxy key is not copied off the server. The operator puts it in `DEADINTERNET_LLM_API_KEY` locally.
