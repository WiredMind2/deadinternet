# Public projects and posting APIs

Tools slice. Retrieved 31 Oct 2026.

Status: ISSUES. Official docs confirm how TikTok, Instagram, and YouTube accept a file and how YouTube and TikTok return view counts, but this pass found no dated operator report of a full generate-then-approve-then-post workflow, and it did not open an official InVideo page.

## Findings

### ShortGPT

https://github.com/RayVentura/ShortGPT

Local framework (Docker or Colab, Gradio on port 31415). From a topic it writes a script, synthesizes voice (EdgeTTS, or ElevenLabs if a key is set), pulls images and footage from the web and Pexels, burns captions, and renders a short. Separate engines cover longer videos and dubbing a finished video into another language. A human supplies API keys, runs the app, and picks language and watermark. The README does not describe uploading to TikTok, Reels, or Shorts, and it does not pull analytics. A `LICENSE` file exists; this pass did not open the license text. README last described as updated 19 Sep 2024; Gemini-key support committed 10 Feb 2025. Source: GitHub README and repo file list, retrieved 31 Oct 2026.

### MoneyPrinter

https://github.com/FujiwaraChoki/MoneyPrinter

Creates YouTube Shorts from a topic with MoviePy. The current README says script and metadata are Ollama-first, so that step can run locally. License text on the repo is MIT, copyright 2024. This pass did not open the full pipeline, so voice, footage, captions, and upload are not confirmed from the README snippet. Source: GitHub README snippet and `LICENSE` file, retrieved 31 Oct 2026.

### MoneyPrinterV2

https://github.com/FujiwaraChoki/MoneyPrinterV2

Rewrite that lists a YouTube Shorts automator on a cron scheduler, plus a Twitter bot, Amazon affiliate posts, and cold email. Python 3.12. It acknowledges KittenTTS and gpt4free. License stated in the README and license file is AGPL-3.0. The README's own disclaimer says it is educational and makes no warranty about completeness. A commit on 26 Mar 2026 is titled as adding a Post Bridge cross-posting integration, and a commit on 15 Sep 2026 adds a custom topic for Shorts. The README body fetched here does not explain Post Bridge, Instagram, or TikTok. A human fills `config.json` and decides to run the scheduler. Source: raw README, retrieved 31 Oct 2026; commit titles from the GitHub file listing in search results.

### MoneyPrinterTurbo

https://github.com/harry0703/MoneyPrinterTurbo

The project's own README, with a resources commit dated 26 Oct 2026, says: give a topic or keyword and it writes a script, matches stock or uploaded footage, adds voice, subtitles, and music, and exports 9:16, 16:9, or 1:1. Interfaces listed are an agent skill, WebUI, API, and CLI. Voice options include Edge TTS with no key. The same README claims one-click upload to TikTok, Instagram, and YouTube Shorts after generation. License shown on the GitHub page is MIT. This pass did not read the publisher source, so the upload claim is the maintainer's, not a verified API call. A human still supplies model and stock API keys and the platform accounts. Source: GitHub README page content, retrieved 31 Oct 2026.

### AutoShorts (two different projects)

https://github.com/SaarD00/AI-Youtube-Shorts-Generator and https://github.com/smith1302/AutoShortsAI

SaarD00, created 24 Dec 2025, MIT, is a Python script: Gemini writes a script, Edge TTS narrates, Pexels supplies two clips per scene, FFmpeg edits, and the MP4 lands in `assets/final/`. It can run unattended via cron. The README does not say it uploads. A human provides keys, ffmpeg, and an optional avatar file.

smith1302/AutoShortsAI points at http://autoshorts.ai/ and describes a hosted service that writes, voices, captions, and posts a new video every day to YouTube and TikTok, or emails the file instead. No price and no license appeared in the README snippet. "Viral-worthy" and "while you sleep" are marketing. Source: both GitHub READMEs, retrieved 31 Oct 2026.

### Newer open-source generators (2025–2026 READMEs)

https://github.com/AbdullahNaveed/ai-shorts-generator. Topic to a 1080×1920 MP4 with script, fal or Pexels/Pixabay visuals, voice, word captions, and music. README says a local dashboard previews and publishes. "Publish" is not shown here as a call to TikTok, Meta, or YouTube. License text not opened.

https://github.com/Chamanrajragu/purffle-shorts. README says MIT, no watermark, and that a topic, URL, Reddit post, or long video becomes a vertical file, then can be uploaded or scheduled to YouTube, TikTok, and Instagram, staying inside YouTube's daily quota. Words such as "viral" and "retention-focused" are the author's marketing. Upload code was not opened.

https://github.com/mutonby/openshorts. Clips a long video into 9:16 with moment detection, face tracking, subtitles, and dubbing. GitHub About says MIT, self-host with Docker, or a hosted GPU plan "from $12/mo." That price is the project's own line. It does not generate a faceless video from a topic.

Sources: GitHub README and About text, retrieved 31 Oct 2026.

### HeyGen

https://developers.heygen.com/docs/quick-start

API at `https://api.heygen.com` with `X-Api-Key`. Video Agent takes a prompt, chooses avatar and voice, and returns an MP4 after polling. Docs also list a photo avatar, a digital twin from video, clips up to 30 seconds (15 seconds from a reference), voice cloning, and templates. A human creates the key and writes the prompt. The quick start does not post to TikTok, Reels, or Shorts, and it does not return views or revenue. Price was not on this page. Source: HeyGen quick start, retrieved 31 Oct 2026.

### Synthesia

https://docs.synthesia.io/reference/introduction and https://developers.synthesia.io/docs/video-api-introduction

Video API creates a file asynchronously: scripted avatar, dub, translation, or a template filled in bulk. A separate Interactive Avatars API is a live lip-synced session, not a file. API access is stated as Pro plans or above. Test videos are capped at 30 per day. Write limits on the Pro tier are 60 requests per minute, 300 per hour, and 1,000 per day. A human writes the script or template and holds the key. These pages do not post to social networks or return channel analytics. Dollar price of Pro was not on these pages. Source: Synthesia docs, retrieved 31 Oct 2026.

### Captions

https://captions.ai/help/docs/intro and https://captions.ai/help/api-reference/build-with-captions

Help center says the product makes a talking-head video from a script or an AI twin, cuts uploaded footage, captions, dubs, and exports 1080p, and that a person can publish from the product to TikTok, Instagram, and YouTube. The developer page says APIs exist for generation and editing, and that any product offered to end users must show "Powered by Captions" linking to captions.ai. "No camera required" and "no editor needed" are marketing on the intro page. Endpoint list, rate limits, and price were not on the pages opened. Source: Captions Help Center, retrieved 31 Oct 2026.

### Opus Clip

https://help.opus.pro/api-reference/overview and https://www.opus.pro/api

Takes a long video and returns short clips. API key from the dashboard. Access is listed for Pro (Beta), Max, and Business. Standard limit is 30 requests per minute per key. Input cap is 10 hours and 30 GB. Projects expire in 30 days unless auto-save is on. The overview lists endpoints to create a project, fetch clips, edit captions, and "publish or schedule clips to connected accounts." This pass did not open that social-posting reference, so which networks and whether analytics come back are not confirmed. Credits are required. Credit price was not stated. Source: Opus Clip API overview, retrieved 31 Oct 2026.

### Vsub

https://vsub.io/docs/api/ai-videos and https://vsub.io/docs/api/mcp

`POST https://api.vsub.io/v1/ai-videos` takes a script (up to 10,000 characters), splits scenes, records a voice-over, generates images, and can render a portrait or landscape MP4. Leaving `render` off keeps an editable project. Captioning an existing video, quiz, fake-text, and Roblox-gameplay videos are separate endpoints. Creation returns immediately. The caller polls or uses a webhook. Rendering spends export credits and requires a paid plan. A human still fixes a bad word or moves captions in the editor. These pages do not post to TikTok, Reels, or Shorts and do not return views. The `2026-08-04` timestamp is sample JSON, not a publication date. Source: Vsub API docs, retrieved 31 Oct 2026.

### InVideo

Not reported. This pass did not open an official InVideo page, so no workflow is stated.

### TikTok Content Posting API

https://developers.tiktok.com/doc/content-posting-api-reference-direct-post and https://developers.tiktok.com/doc/content-sharing-guidelines

`POST /v2/post/publish/video/init/` with scope `video.publish` posts a video the user has authorized. The caller pulls from a verified URL or uploads to a URL that lasts one hour. `is_aigc: true` adds TikTok's "Creator labeled as AI-generated" tag. Each user token is limited to 6 requests per minute on the direct-post init call. Creator-info query is 20 requests per minute. Unaudited clients can post only as private, and only for up to 5 users in 24 hours. Audited and unaudited clients share a per-creator cap that TikTok says may vary and is "typically around 15 posts per day," across all Direct Post clients. Photo upload docs add a cap of 5 pending shares in any 24 hours. The API does not approve content for the human. The human's app decides when to call it. It does not return revenue. Sources: TikTok developer docs, retrieved 31 Oct 2026.

### TikTok video query

https://developers.tiktok.com/doc/tiktok-api-v2-video-query. Last updated 24 Aug 2026.

`POST /v2/video/query/` with scope `video.list` returns details for up to 20 video IDs that belong to the authorized user. Requested fields can include `view_count`, `like_count`, `comment_count`, and `share_count`. The page does not list revenue or outbound clicks. The caller must already know the video IDs. Source: TikTok docs, retrieved 31 Oct 2026.

### Instagram content publishing

https://developers.facebook.com/docs/instagram-platform/content-publishing. Updated 20 Oct 2026.

Professional accounts only. Publish is two calls: create a container at `/{ig-id}/media`, then `/{ig-id}/media_publish`. A Reel sets `media_type=REELS` and a public `video_url`, or uses a resumable upload. Meta fetches the URL, so the file must be public at publish time. Containers not published within 24 hours expire. `is_ai_generated=true` is the self-disclosure flag. After publish, `media_type` comes back as `VIDEO`. `media_product_type` is how you tell it was a Reel. The rate-limit section says 100 API-published posts in a moving 24-hour window, checked on `media_publish`. The carousel section of the same page says accounts are limited to 50 published posts in 24 hours. This page does not document view counts, clicks, or revenue. Source: Meta Instagram Platform docs, retrieved 31 Oct 2026.

### YouTube upload

https://developers.google.com/youtube/data/reference/rest/v3/videos/insert and https://developers.google.com/youtube/v3/determine_quota_cost

`videos.insert` uploads a video up to 256 GB. Default project quota is 100 insert calls per day, each costing 1 unit in its own bucket, resetting at midnight Pacific. Scope `youtube.upload` is sufficient. The body can set title, description, privacy, `publishAt`, and `status.containsSyntheticMedia`. The insert page says videos from unverified API projects are not forced to private. Nothing on these pages makes the upload a Short. Shorts are a YouTube classification of a short vertical upload, not a separate method in the pages opened. Source: Google YouTube Data API docs, retrieved 31 Oct 2026.

### YouTube Analytics

https://developers.google.com/youtube/analytics/metrics

The Analytics API defines per-video metrics including `views`, `likes`, `comments`, `shares`, `averageViewDuration`, `cardClicks`, `cardClickRate`, and `estimatedRevenue`. Estimated revenue is net, estimated, subject to month-end adjustment, excludes partner-sold and partner-served ads, and defaults to USD. This page does not state the OAuth scope or the partner-program requirement. Source: Google YouTube Analytics metrics, retrieved 31 Oct 2026.

### What operators say works

No source in this pass was a review that names a workflow and a date. GitHub READMEs and help centers are vendor or author claims. They are not treated as operator reports.

## Conflicts

The Instagram content-publishing page, updated 20 Oct 2026, states both a 100-post cap per moving 24 hours and, under carousel limits, a 50-post cap per 24 hours. Both are on that page.

A Phyllo article titled as a 2026 Reels guide says most accounts can post Reels up to 90 seconds, some still hit 60 seconds, and insights require 1,000 followers and cover organic engagement only. The Meta page opened here states neither duration nor the follower gate. Phyllo sells a cross-platform data API, so that article is a secondary source. https://www.getphyllo.com/post/a-complete-guide-to-the-instagram-reels-api

TikTok's own guidelines say the daily creator cap "may vary" and is "typically around 15." That is not a fixed quota.

MoneyPrinterTurbo's README claims it uploads to TikTok, Instagram, and YouTube Shorts. The posting code was not read, so that remains a maintainer claim.

## Inferences

Inference: a lab that must approve each file before posting matches the tools that stop at an MP4 (ShortGPT, MoneyPrinter, SaarD00, Vsub with render left off). Cron posters such as MoneyPrinterV2's scheduler and AutoShorts.ai's daily post do the opposite of that gate.

Inference: views can be pulled per video from YouTube Analytics and from TikTok `video.query` once the video ID is known. Estimated revenue is documented only on YouTube in the pages opened. A single revenue number across TikTok, Reels, and Shorts is not provided by these APIs.

Inference: the official post APIs do not include a human-approval step. Approval is whatever the caller does before it sends the publish request. TikTok's unaudited private-only rule is an extra platform gate, not a review UI.

Inference: setting `is_aigc`, `is_ai_generated`, or `containsSyntheticMedia` is how those three APIs expose an AI label. The pages describe the fields. They do not say every AI video must use them.

## Sources

- ShortGPT README, https://github.com/rayventura/shortgpt/blob/stable/README.md. Local script, voice, footage, captions, and render. No upload described.
- ShortGPT repo listing, https://github.com/RayVentura/ShortGPT/tree/stable. Gemini support committed 10 Feb 2025. README updated 19 Sep 2024.
- MoneyPrinter LICENSE, https://github.com/FujiwaraChoki/MoneyPrinter/blob/main/LICENSE. MIT, copyright 2024.
- MoneyPrinter README, https://github.com/FujiwaraChoki/MoneyPrinter/blob/main/README.md. Topic to a YouTube Short. Ollama-first script and metadata.
- MoneyPrinterV2 README, https://raw.githubusercontent.com/FujiwaraChoki/MoneyPrinterV2/main/README.md. Shorts cron job, AGPL-3.0, educational disclaimer.
- MoneyPrinterV2 file listing, https://github.com/FujiwaraChoki/MoneyPrinterV2. Post Bridge commit title 26 Mar 2026. Custom topic 15 Sep 2026.
- MoneyPrinterTurbo README, https://github.com/harry0703/MoneyPrinterTurbo. Topic to a vertical file. README claims TikTok, Instagram, and Shorts upload. MIT on the repo page. Resources commit 26 Oct 2026.
- SaarD00 README, https://github.com/SaarD00/AI-Youtube-Shorts-Generator. MIT faceless pipeline to a local MP4. Created 24 Dec 2025.
- smith1302 README, https://github.com/smith1302/AutoShortsAI. Hosted daily post to YouTube and TikTok, or email the file.
- ai-shorts-generator README, https://github.com/AbdullahNaveed/ai-shorts-generator. Topic to 1080×1920 with a local preview dashboard.
- PurffleShorts README, https://github.com/Chamanrajragu/purffle-shorts. Author claims MIT and upload or schedule to YouTube, TikTok, and Instagram.
- OpenShorts About, https://github.com/mutonby/openshorts. Long video to 9:16 clips. MIT self-host. "from $12/mo" is the project's price line.
- HeyGen Quick Start, https://developers.heygen.com/docs/quick-start. Prompt to an avatar MP4. No social post.
- Synthesia API introduction, https://docs.synthesia.io/reference/introduction. File API versus live interactive avatars.
- Synthesia Video API, https://developers.synthesia.io/docs/video-api-introduction. Pro or above. 30 test videos per day. Pro write limits.
- Captions intro, https://captions.ai/help/docs/intro. Talking-head or edit, then publish from the product to TikTok, Instagram, and YouTube.
- Captions build page, https://captions.ai/help/api-reference/build-with-captions. End-user apps must show "Powered by Captions."
- Opus Clip API overview, https://help.opus.pro/api-reference/overview. 30 requests per minute. 10 hours and 30 GB. 30-day expiry. Social publish listed but not opened.
- Vsub AI video, https://vsub.io/docs/api/ai-videos. Script to narrated scenes. Render is optional and paid.
- Vsub MCP, https://vsub.io/docs/api/mcp. Caption, quiz, fake-text, and Roblox endpoints. No social post on this page.
- TikTok Direct Post, https://developers.tiktok.com/doc/content-posting-api-reference-direct-post. 6 requests per minute per user token. Private-only if unaudited. `is_aigc`.
- TikTok sharing guidelines, https://developers.tiktok.com/doc/content-sharing-guidelines. Unaudited cap of 5 users per 24 hours. Creator cap typically around 15 posts per day.
- TikTok Query Videos, https://developers.tiktok.com/doc/tiktok-api-v2-video-query. `view_count` and engagement counts for up to 20 IDs. Updated 24 Aug 2026.
- Instagram Content Publishing, https://developers.facebook.com/docs/instagram-platform/content-publishing. Reel container plus publish. 100-post and 50-post sentences. Updated 20 Oct 2026.
- YouTube videos.insert, https://developers.google.com/youtube/data/reference/rest/v3/videos/insert. Upload to 256 GB. `containsSyntheticMedia`. Unverified projects are not forced private.
- YouTube quota, https://developers.google.com/youtube/v3/determine_quota_cost. 100 `videos.insert` calls per day by default.
- YouTube Analytics metrics, https://developers.google.com/youtube/analytics/metrics. `views`, card clicks, and `estimatedRevenue`.
- Phyllo Reels guide, https://www.getphyllo.com/post/a-complete-guide-to-the-instagram-reels-api. Third-party claims of 60/90-second duration and a 1,000-follower insights gate. Not confirmed on the Meta page opened here.

## Second pass additions

A second tools pass retrieved 31 Oct 2026. It repeats ShortGPT, MoneyPrinterTurbo, HeyGen, Vsub, TikTok Direct Post, and YouTube upload. The items below are the facts that pass did not already record, plus conflicts between the two passes.

### MoneyPrinter cookie upload

The current FujiwaraChoki README, retrieved 31 Oct 2026, tells the operator to copy a TikTok `sessionid` cookie from a logged-in browser. It also describes a Docker queue with an API, a worker, and Postgres, and says pull requests are not accepted for the time being. That README does not document YouTube OAuth, Instagram, analytics, or an approval step. https://github.com/FujiwaraChoki/MoneyPrinter

### hpan fork and the private-upload warning

https://github.com/hpan/MoneyPrinter says the project is deprecated and points at V2. It documents YouTube OAuth with scopes `youtube`, `youtube.upload`, and `youtubepartner`, videos private by default, and a warning that uploads from an unverified API project stay private and cannot be appealed. Fork metadata in the search snapshot says MIT, created 1 Mar 2024. The current Google `videos.insert` page says unverified API projects are not forced private. The Google page is the later official source. The fork matches an older YouTube policy.

### MoneyPrinterTurbo publisher and package name

The GitHub page summary reported 136,573 stars. That count is GitHub's number on the day of the fetch, not a quality score. Release v1.2.6 is dated 10 May 2025. The releases page lists v1.3.9 on "21 Oct" without a year in the excerpt, and that note says Upload-Post tracking handles were preserved. The README says the tool publishes to TikTok, Instagram, and YouTube Shorts, and it does not name Upload-Post. Both can be true if Upload-Post is the publisher. The official PyPI name is `mpt`. A package named `MoneyPrinterTurbo` on PyPI is a third party. Python 3.11 or newer. https://github.com/harry0703/MoneyPrinterTurbo/releases

### AutoShorts is not one project

Three more repos use the name, separate from SaarD00 and smith1302:

- https://github.com/NYOGamesCOM/AutoAI documents a local FastAPI. `POST /api/runs` clips a long video. `POST /api/publish` takes `youtube`, `tiktok`, `facebook`, or `instagram`, and `mode` of `api` or `browser`. Credentials sit in a local folder. The sample run folder is dated 2026-04-20.
- https://github.com/JayWebtech/autoshorts is a local Tauri app that ranks 9:16 candidates. The excerpt does not show a post step.
- https://github.com/divyaprakash0426/autoshorts clips long video, including gameplay, with Whisper and optional local voice. The excerpt does not show a post step.

### HeyGen duration conflict

The quick start says clips up to 30 seconds, and 15 seconds from a reference. The create-video reference says one avatar request is one scene and the script or audio must stay within 30 minutes. `POST /v3/videos` with `type: "avatar"` accepts `9:16`. Photo avatars are trained from an uploaded headshot. These are two official pages retrieved the same day. They were not reconciled. https://developers.heygen.com/reference/create-video and https://developers.heygen.com/generate-avatar-video

### Captions prices are third-party

The second pass did not open a Captions-owned doc. https://github.com/api-evangelist/captions-ai quotes $0.15 per minute for captions and 1 credit per second for avatar video, and it says it is not the company's API. Treat those prices as unverified. The first pass's Captions Help Center pages stay the official source for publishing from the product.

### YouTube analytics scopes

`reports.query` uses `yt-analytics.readonly` for activity metrics such as views, and `yt-analytics-monetary.readonly` for estimated revenue. The channel's most-viewed-videos report returns at most 200 rows. Click counts were not named on the retrieved Analytics pages. https://developers.google.com/youtube/analytics/reference

### Instagram host conflict

Doc snippets disagree on `graph.instagram.com/v26.0` versus `graph.facebook.com/v22.0`. Both came from Facebook docs in the same search. The second pass did not read the publishing page body before its cap, so the host was not resolved.

### What the second pass still did not find

No dated operator report of a generate, approve, then post workflow. InVideo was still not opened on an official page. None of the generators implement an approval gate. A caller can sit between the file and the publish call. That is a composition, not a feature a README describes. Per-video view and revenue pullback is documented for YouTube. TikTok query returns view and engagement counts, from the first pass, and does not return revenue. Outbound click tracking was not found on these product pages.
