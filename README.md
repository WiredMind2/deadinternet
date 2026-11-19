# Dead Internet

A local lab for short vertical video. It makes each video as a faceless edit or with an AI presenter, then waits for approval before a post to TikTok, Reels, or YouTube Shorts. Each video is an experiment. Revenue and clicks are the score. Views are a clue.

## Run

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m deadinternet
```

The dashboard is in `web/`. CI runs the backend suite and the dashboard build. Coverage on the `deadinternet` package must stay at 85% or higher. The API listens on `127.0.0.1:8000`. Avatar renders need `AVATAR_API_KEY`. Faceless renders need `ffmpeg` on `PATH`.

### Dashboard

```powershell
cd web
npm ci
npm run dev
```

Then open the printed `localhost` URL. `npm ci` is required once per clone: a stale or
partial `node_modules` makes `vite` fail with "'vite' is not recognized". The dev server
binds `localhost`, not `127.0.0.1`, and proxies API calls to the backend.

### Known issue: Python 3.14 and langchain

On Python 3.14 the suite passes but `langchain-core` warns that its Pydantic V1 shim
"isn't compatible with Python 3.14 or greater". The live suggest agent boots and its
offline tests pass, but a real model call on 3.14 is unverified. Treat 3.12 or 3.13 as
the safe interpreters for live `Suggest` until langchain drops the shim.
