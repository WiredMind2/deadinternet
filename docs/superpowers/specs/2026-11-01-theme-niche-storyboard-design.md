# Theme folders and storyboard approval

A theme is a broad topic. A niche is one series under that theme. Every video in a niche shares one folder, and that folder holds the storyboard and the rendered file for each video. A video cannot render until its storyboard is approved. The finished-file check before posting stays.

## Terms

- A theme has an id, a name, and a language. Today's niche catalog rows become themes.
- A niche has an id, a theme, and a name. The niche id is unique in the lab, so a series belongs to one theme.
- A video is still an experiment. It belongs to one niche. The theme comes from that niche.
- A score cell is the niche, the style, and the money path. Two niches under one theme score apart.

## Migration

On open, if the `niches` table still has a `language` column, one transaction does all of the following:

1. Rename that table to `themes`.
2. Create `niches (id, theme_id, name)`.
3. Copy each old row into a niche with the same id, pointing at the theme of that id.

Existing videos keep their cell. Their folder is `media/{id}/{id}/`.

## Folder

The media directory is the one the API already chooses, beside the database.

```
media/{theme}/{niche}/{video}.storyboard.json
media/{theme}/{niche}/{video}.mp4
```

Theme, niche, and video ids are a single folder name. Empty, `.`, `..`, a slash, and a backslash are rejected. The storyboard file is the only copy of the beats:

```json
{
  "beats": [
    {
      "spoken": "...",
      "on_screen": "...",
      "visual_note": "..."
    }
  ]
}
```

Array order is the cut order. The script is the spoken lines joined by newlines. On-screen text and the visual note may be empty. The file is UTF-8 JSON with keys in the order `spoken`, `on_screen`, `visual_note`, two-space indent, and a trailing newline. The board hash is the sha256 hex of those bytes.

Render speaks the script. It does not read the visual note. The dashboard reads and writes the file only through the API.

## Gate

`draft` can approve the board. Approval requires at least one beat and a non-empty spoken line on every beat. That moves the video to `board_approved` and stores the hash.

Render starts from `board_approved`, and again from `render_failed` when the hash still matches. `draft` cannot render. Render reads the file again and checks the hash before spending a daily render. A mismatch returns 409 and moves the video back to `draft` without spending a render. A missing or unreadable file returns 422 and does not change status.

Saving the board writes the file, then sets the script from the spoken lines. A later read takes the beats from the file if the database update failed. Save is allowed from `draft`, `board_approved`, and `render_failed`. The last two return the video to `draft` and clear the hash. Save during render, file review, or after a post returns 409 and leaves the file untouched. A rejected, approved, live, or complete video keeps the board it had. A failed render keeps the storyboard file.

Unknown theme, unknown niche, and a bad id return 422. Creating a video and running the starter grid both require a niche that already exists.

File review, posting, and completion are unchanged.

## API

- `POST /themes` with `id`, `name`, and `language`. `POST /niches` with `id`, `theme_id`, and `name`.
- `GET /catalog` returns themes and niches, plus the existing presenter, voice, offer, and hook ids.
- `POST /experiments` accepts `beats`, or the current single `script`, which is stored as one beat. It writes the storyboard file. Status is `draft`.
- `GET /experiments/{id}/storyboard` and `PUT /experiments/{id}/storyboard`.
- `POST /experiments/{id}/approve-board`.
- `POST /experiments/{id}/render` passes the niche folder as the media directory. The existing renderers write `{id}.mp4` there.

Starter and suggest emit a template beat list. Suggest copies the parent video's niche. They do not call a language model.

## Dashboard

Catalog gains a theme field and keeps niche as the series id, with actions to add a theme and a niche before the starter grid or a saved draft. The selected video on Board shows the beat list, save, and approve while the video is still before the finished file. Render stays disabled until the board is approved. Proposals shows the beats, and accepting one creates the video and the file. Review, Post, and Results stay. Results still titles a row with niche, style, and money path, which is now the series cell.

## Tests

Domain tests cover the new transitions, the spoken-line rule, the joined script, and two niches under one theme scoring as different cells. File tests cover a round trip and a rejected path. Store tests cover the migration. API tests cover create, save, approve, render into the niche folder, a draft render refused, a changed file refused, an unknown niche, and starter writing one storyboard file per video. Package coverage stays at 85% or higher. The beat list on Board is checked in the browser.
