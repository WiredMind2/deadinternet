# Dead Internet

A local lab for short vertical video. It makes each video as a faceless edit or with an AI presenter, then waits for approval before a post to TikTok, Reels, or YouTube Shorts. Each video is an experiment. Revenue and clicks are the score. Views are a clue.

## Run

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m deadinternet
```

The dashboard is in `web/`. CI runs the backend suite and the dashboard build. Coverage on the `deadinternet` package must stay at 85% or higher. The API listens on `127.0.0.1:8000`. Avatar renders need `AVATAR_API_KEY`. Faceless renders need `ffmpeg` on `PATH`.
