import { useEffect, useMemo, useRef, useState } from "react";

const SCREENS = ["Board", "Review", "Post", "Results", "Proposals", "Catalog"];
const PLATFORMS = ["tiktok", "instagram", "youtube"];
const STATUSES = [
  "draft",
  "board_approved",
  "rendering",
  "render_failed",
  "in_review",
  "rejected",
  "approved",
  "live",
  "complete",
];
const STYLE_KINDS = ["faceless", "avatar"];
const MONEY_KINDS = ["affiliate", "platform_payout", "own_offer"];

function styleKind(row) {
  const style = row?.style;
  if (!style) return "";
  if (typeof style === "string") return style;
  return style.kind || "";
}

function moneyKind(row) {
  const money = row?.money;
  if (!money) return "";
  if (typeof money === "string") return money;
  return money.kind || "";
}

function viewsOf(row) {
  if (!row || typeof row !== "object") return undefined;
  if (row.views !== undefined && row.views !== null) return row.views;
  if (row.view_count !== undefined && row.view_count !== null) return row.view_count;
  return undefined;
}

function blank(value) {
  return value === undefined || value === null || value === "";
}

function show(value) {
  return blank(value) ? "—" : String(value);
}

function unique(values) {
  return [...new Set(values.filter((value) => !blank(value)))].sort((a, b) =>
    String(a).localeCompare(String(b)),
  );
}

function unwrapList(data) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== "object") return [];
  for (const key of [
    "experiments",
    "results",
    "rows",
    "cells",
    "drafts",
    "proposals",
    "items",
    "data",
  ]) {
    if (Array.isArray(data[key])) return data[key];
  }
  if (data.factor_diffs || data.niche_id || data.id) return [data];
  return [];
}

function errorMessage(error) {
  const detail = error?.data?.detail ?? error?.data?.message;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "string" ? item : item?.msg || ""))
      .filter(Boolean)
      .join(" ");
  }
  return error?.message || "Request failed";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    const error = new Error("Request failed");
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function videoSrc(experiment) {
  if (!experiment?.id || blank(experiment.file_path)) return "";
  return `/media/${encodeURIComponent(experiment.id)}`;
}

function tiktokTooShort(row) {
  return (
    moneyKind(row) === "platform_payout" &&
    row?.money?.platform === "tiktok" &&
    Number(row.length_sec) <= 60
  );
}

const NEXT_STEP = {
  draft: "Save the storyboard, then approve the board to unlock render.",
  board_approved: "Render is unlocked.",
  rendering: "A render is in progress.",
  render_failed: "Rendering failed. Fix the problem, then retry the render.",
  in_review: "Open Review to approve or reject this cut.",
  approved: "Open Post to publish it.",
  live: "Record views on Post, then complete the experiment.",
  rejected: "This experiment was rejected.",
  complete: "Suggest can use this closed experiment.",
};

const TIKTOK_LENGTH =
  "TikTok Creator Rewards videos must be longer than 60 seconds. This one cannot be approved.";

function idList(value) {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") return item.id || item.niche_id || "";
        return "";
      })
      .filter(Boolean);
  }
  if (typeof value === "object") return Object.keys(value);
  return [];
}

function normalizeCatalog(data) {
  const source = data?.catalog && typeof data.catalog === "object" ? data.catalog : data || {};
  return {
    themes: idList(source.theme_ids || source.themes),
    niches: idList(source.niche_ids || source.niches),
    voices: idList(source.voice_ids || source.voices),
    presenters: idList(source.presenter_ids || source.presenters),
    hooks: idList(source.hook_ids || source.hooks),
  };
}

function splitIds(value) {
  return value
    .split(/[\s,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function moneyPayload(kind, platform, trackingCode, merchant, offerUrl) {
  if (kind === "affiliate") {
    return { kind, tracking_code: trackingCode.trim(), merchant: merchant.trim() };
  }
  if (kind === "own_offer") {
    return { kind, tracking_code: trackingCode.trim(), offer_url: offerUrl.trim() };
  }
  return { kind: "platform_payout", platform };
}

function styleFromForm(voiceId, presenterId) {
  if (presenterId.trim()) {
    return {
      kind: "avatar",
      presenter_id: presenterId.trim(),
      voice_id: voiceId.trim(),
    };
  }
  return {
    kind: "faceless",
    look: "stills",
    voice_id: voiceId.trim(),
    caption_style: "bold",
  };
}

function draftPayload(draft) {
  return {
    niche_id: draft.niche_id,
    hook_id: draft.hook_id,
    hypothesis: draft.hypothesis ?? "",
    script: draft.script ?? "",
    caption: draft.caption ?? "",
    length_sec: draft.length_sec,
    style: draft.style,
    money: draft.money,
    ...(draft.language ? { language: draft.language } : {}),
    ...(draft.proposal_id ? { proposal_id: draft.proposal_id } : {}),
    ...(Array.isArray(draft.beats) ? { beats: draft.beats } : {}),
  };
}

function publicationFrom(data) {
  if (!data || typeof data !== "object") return null;
  if (data.publication && typeof data.publication === "object") return data.publication;
  return data;
}

function emptyPlatformRow() {
  return { account_id: "", token: "", url: "", views: "", publication: null };
}

function Facts({ rows }) {
  return (
    <dl className="facts">
      {rows.map((row) => (
        <div key={row.label} className={row.wide ? "wide" : undefined}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function TrackingLink({ code }) {
  const [copied, setCopied] = useState(false);
  const url = `${window.location.origin}/r/${code}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <span className="tracking-link">
      <code>{url}</code>
      <button type="button" onClick={copy} aria-label={`Copy tracking link ${url}`}>
        {copied ? "Copied" : "Copy"}
      </button>
      {!copied ? null : <span role="status">Link copied to the clipboard.</span>}
    </span>
  );
}

function experimentFacts(experiment, { includeCopy = true } = {}) {
  const style = experiment.style && typeof experiment.style === "object" ? experiment.style : {};
  const money = experiment.money && typeof experiment.money === "object" ? experiment.money : {};
  const rows = [
    { label: "id", value: show(experiment.id) },
    { label: "status", value: show(experiment.status) },
    { label: "theme_id", value: show(experiment.theme_id) },
    { label: "niche_id", value: show(experiment.niche_id) },
    { label: "hook_id", value: show(experiment.hook_id) },
    { label: "hypothesis", value: show(experiment.hypothesis), wide: true },
    { label: "length_sec", value: show(experiment.length_sec) },
    { label: "style.kind", value: show(styleKind(experiment)) },
    { label: "money.kind", value: show(moneyKind(experiment)) },
    { label: "revenue_cents", value: show(experiment.revenue_cents) },
    { label: "clicks", value: show(experiment.clicks) },
    { label: "file_path", value: show(experiment.file_path), wide: true },
    { label: "approved_at", value: show(experiment.approved_at) },
  ];
  if (style.look) rows.push({ label: "look", value: show(style.look) });
  if (style.voice_id) rows.push({ label: "voice_id", value: show(style.voice_id) });
  if (style.presenter_id) rows.push({ label: "presenter_id", value: show(style.presenter_id) });
  if (style.caption_style) rows.push({ label: "caption_style", value: show(style.caption_style) });
  if (money.platform) rows.push({ label: "platform", value: show(money.platform) });
  if (money.merchant) rows.push({ label: "merchant", value: show(money.merchant) });
  if (money.tracking_code) rows.push({ label: "tracking_code", value: show(money.tracking_code) });
  if (money.offer_url) rows.push({ label: "offer_url", value: show(money.offer_url), wide: true });
  if (experiment.render_error) {
    rows.push({ label: "render_error", value: show(experiment.render_error), wide: true });
  }
  if ((money.kind === "affiliate" || money.kind === "own_offer") && money.tracking_code) {
    rows.push({ label: "tracking link", value: <TrackingLink code={money.tracking_code} /> });
  }
  if (includeCopy) {
    rows.push(
      { label: "script", value: show(experiment.script), wide: true },
      { label: "caption", value: show(experiment.caption), wide: true },
    );
  }
  return rows;
}

function SelectFilter({ id, label, value, onChange, options }) {
  return (
    <div className="filter">
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

function Banner({ tone = "error", children }) {
  if (!children) return null;
  return (
    <p className={tone === "ok" ? "banner ok" : "banner"} role={tone === "ok" ? "status" : "alert"}>
      {children}
    </p>
  );
}

const EDITABLE_BOARD = new Set(["draft", "board_approved", "render_failed"]);

function StoryboardEditor({ experiment, onChanged }) {
  const keyRef = useRef(1);
  const [beats, setBeats] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  function keyed(rows) {
    return rows.map((beat) => ({
      spoken: beat.spoken || "",
      on_screen: beat.on_screen || "",
      visual_note: beat.visual_note || "",
      key: `beat-${keyRef.current++}`,
    }));
  }

  useEffect(() => {
    let cancelled = false;
    setError("");
    api(`/experiments/${encodeURIComponent(experiment.id)}/storyboard`)
      .then((data) => {
        if (!cancelled) setBeats(keyed(Array.isArray(data.beats) ? data.beats : []));
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [experiment.id]);

  function updateBeat(key, field, value) {
    setBeats((current) =>
      current.map((beat) => (beat.key === key ? { ...beat, [field]: value } : beat)),
    );
  }

  function payload() {
    return beats.map((beat) => ({
      spoken: beat.spoken,
      on_screen: beat.on_screen,
      visual_note: beat.visual_note,
    }));
  }

  async function save(event) {
    event.preventDefault();
    setBusy("save");
    setError("");
    try {
      await api(`/experiments/${encodeURIComponent(experiment.id)}/storyboard`, {
        method: "PUT",
        body: JSON.stringify({ beats: payload() }),
      });
      await onChanged(`Saved the storyboard for ${experiment.id}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function approveBoard() {
    setBusy("approve");
    setError("");
    try {
      await api(`/experiments/${encodeURIComponent(experiment.id)}/storyboard`, {
        method: "PUT",
        body: JSON.stringify({ beats: payload() }),
      });
      await api(`/experiments/${encodeURIComponent(experiment.id)}/approve-board`, {
        method: "POST",
      });
      await onChanged(`Approved the storyboard for ${experiment.id}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function renderVideo() {
    setBusy("render");
    setError("");
    try {
      await api(`/experiments/${encodeURIComponent(experiment.id)}/render`, { method: "POST" });
      await onChanged(`Rendered ${experiment.id}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  if (!EDITABLE_BOARD.has(experiment.status)) return null;

  return (
    <form onSubmit={save}>
      <fieldset>
        <legend>Storyboard</legend>
        <Banner>{error}</Banner>
        {beats.length === 0 ? <p>Add a beat before approving this board.</p> : null}
        <ol className="stack">
          {beats.map((beat, index) => (
            <li key={beat.key}>
              <fieldset>
                <legend>Beat {index + 1}</legend>
                <div className="filter">
                  <label htmlFor={`${beat.key}-spoken`}>Spoken line</label>
                  <textarea
                    id={`${beat.key}-spoken`}
                    name="spoken"
                    value={beat.spoken}
                    onChange={(event) => updateBeat(beat.key, "spoken", event.target.value)}
                  />
                </div>
                <div className="filter">
                  <label htmlFor={`${beat.key}-screen`}>On-screen text</label>
                  <input
                    id={`${beat.key}-screen`}
                    name="on_screen"
                    type="text"
                    value={beat.on_screen}
                    onChange={(event) => updateBeat(beat.key, "on_screen", event.target.value)}
                  />
                </div>
                <div className="filter">
                  <label htmlFor={`${beat.key}-visual`}>Visual note</label>
                  <input
                    id={`${beat.key}-visual`}
                    name="visual_note"
                    type="text"
                    value={beat.visual_note}
                    onChange={(event) => updateBeat(beat.key, "visual_note", event.target.value)}
                  />
                </div>
                <button
                  type="button"
                  className="danger"
                  onClick={() => setBeats((current) => current.filter((item) => item.key !== beat.key))}
                >
                  Remove beat {index + 1}
                </button>
              </fieldset>
            </li>
          ))}
        </ol>
        <div className="actions">
          <button
            type="button"
            onClick={() =>
              setBeats((current) => [
                ...current,
                { spoken: "", on_screen: "", visual_note: "", key: `beat-${keyRef.current++}` },
              ])
            }
          >
            Add beat
          </button>
          <button type="submit" disabled={Boolean(busy)}>
            Save storyboard
          </button>
          <button
            type="button"
            onClick={approveBoard}
            disabled={Boolean(busy) || experiment.status !== "draft"}
          >
            Approve board
          </button>
          <button
            type="button"
            onClick={renderVideo}
            disabled={
              Boolean(busy) ||
              !(experiment.status === "board_approved" || experiment.status === "render_failed")
            }
          >
            {experiment.status === "render_failed" ? "Retry render" : "Render"}
          </button>
        </div>
      </fieldset>
    </form>
  );
}

function Board({ experiments, selectedId, onSelect, onRefresh, onChanged, error }) {
  const [niche, setNiche] = useState("");
  const [style, setStyle] = useState("");
  const [money, setMoney] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState("");

  async function completeVideo() {
    if (!selected || selected.status !== "live") return;
    setBusy("complete");
    setActionError("");
    try {
      await api(`/experiments/${encodeURIComponent(selected.id)}/complete`, { method: "POST" });
      await onChanged(`Completed ${selected.id}.`);
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  const filtered = useMemo(
    () =>
      experiments.filter((row) => {
        if (niche && row.niche_id !== niche) return false;
        if (style && styleKind(row) !== style) return false;
        if (money && moneyKind(row) !== money) return false;
        if (status && row.status !== status) return false;
        return true;
      }),
    [experiments, niche, style, money, status],
  );

  const selected = experiments.find((row) => row.id === selectedId) || null;

  return (
    <>
      <Banner>{error}</Banner>
      <search className="filters">
        <SelectFilter
          id="filter-niche"
          label="niche_id"
          value={niche}
          onChange={setNiche}
          options={unique(experiments.map((row) => row.niche_id))}
        />
        <SelectFilter
          id="filter-style"
          label="style.kind"
          value={style}
          onChange={setStyle}
          options={unique([...STYLE_KINDS, ...experiments.map(styleKind)])}
        />
        <SelectFilter
          id="filter-money"
          label="money.kind"
          value={money}
          onChange={setMoney}
          options={unique([...MONEY_KINDS, ...experiments.map(moneyKind)])}
        />
        <SelectFilter
          id="filter-status"
          label="status"
          value={status}
          onChange={setStatus}
          options={unique([...STATUSES, ...experiments.map((row) => row.status)])}
        />
        <button type="button" onClick={onRefresh}>
          Refresh
        </button>
      </search>
      <p className="meta">
        {filtered.length} shown
        {filtered.length !== experiments.length ? ` of ${experiments.length}` : ""}
      </p>
      <div className="workspace">
        <div className="table-wrap">
          <table>
            <caption>Experiments</caption>
            <thead>
              <tr>
                <th scope="col">id</th>
                <th scope="col">status</th>
                <th scope="col">niche_id</th>
                <th scope="col">style.kind</th>
                <th scope="col">money.kind</th>
                <th scope="col">hook_id</th>
                <th scope="col">length_sec</th>
                <th scope="col">revenue_cents</th>
                <th scope="col">clicks</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={9}>No experiments match these filters.</td>
                </tr>
              ) : (
                filtered.map((row) => (
                  <tr
                    key={row.id}
                    aria-selected={row.id === selectedId}
                    onClick={() => onSelect(row.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(row.id);
                      }
                    }}
                    tabIndex={0}
                  >
                    <td className="mono">{row.id}</td>
                    <td>
                      <span className={`status status-${row.status}`}>{row.status}</span>
                    </td>
                    <td>{show(row.niche_id)}</td>
                    <td>{show(styleKind(row))}</td>
                    <td>{show(moneyKind(row))}</td>
                    <td>{show(row.hook_id)}</td>
                    <td>{show(row.length_sec)}</td>
                    <td>{show(row.revenue_cents)}</td>
                    <td>{show(row.clicks)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <section className="panel">
          <h2>Selected</h2>
          <Banner>{actionError}</Banner>
          {selected ? (
            <>
              <p>{NEXT_STEP[selected.status] || ""}</p>
              {tiktokTooShort(selected) ? <Banner>{TIKTOK_LENGTH}</Banner> : null}
              <Facts rows={experimentFacts(selected)} />
            </>
          ) : (
            <p>Select a row.</p>
          )}
          {selected && selected.status === "live" ? (
            <div className="actions">
              <button type="button" onClick={completeVideo} disabled={Boolean(busy)}>
                Complete
              </button>
            </div>
          ) : null}
          {selected ? <StoryboardEditor experiment={selected} onChanged={onChanged} /> : null}
        </section>
      </div>
    </>
  );
}

function Review({ experiments, selectedId, onSelect, onChanged }) {
  const queue = experiments.filter((row) => row.status === "in_review");
  const selected = queue.find((row) => row.id === selectedId) || queue[0] || null;
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [videoBroken, setVideoBroken] = useState(false);
  const src = videoSrc(selected);
  const tooShort = tiktokTooShort(selected);

  useEffect(() => {
    setVideoBroken(false);
  }, [selected?.id]);

  async function approve() {
    if (!selected) return;
    setBusy("approve");
    setError("");
    try {
      await api(`/experiments/${encodeURIComponent(selected.id)}/approve`, {
        method: "POST",
        body: JSON.stringify({ now: new Date().toISOString() }),
      });
      await onChanged(`Approved ${selected.id}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function reject() {
    if (!selected) return;
    setBusy("reject");
    setError("");
    try {
      await api(`/experiments/${encodeURIComponent(selected.id)}/reject`, { method: "POST" });
      await onChanged(`Rejected ${selected.id}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <Banner>{error}</Banner>
      {tooShort ? <Banner>{TIKTOK_LENGTH}</Banner> : null}
      {queue.length === 0 ? <p>Nothing is in review. Render a draft from the Board.</p> : null}
      <div className="workspace">
        <ul className="picker">
          {queue.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                aria-pressed={selected?.id === row.id}
                onClick={() => onSelect(row.id)}
              >
                <span className="mono">{row.id}</span>
                <span>{row.niche_id}</span>
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <article className="panel">
            <h2 className="mono">{selected.id}</h2>
            <figure className="stage">
              {src && !videoBroken ? (
                <video
                  controls
                  width="270"
                  height="480"
                  src={src}
                  playsInline
                  onError={() => setVideoBroken(true)}
                />
              ) : (
                <p>{src ? "The rendered file could not be played." : "No rendered file yet."}</p>
              )}
              <figcaption>
                file_path <code>{show(selected.file_path)}</code>
              </figcaption>
            </figure>
            <section>
              <h3>Script</h3>
              <pre tabIndex={0}>
                <code>{show(selected.script)}</code>
              </pre>
            </section>
            <section>
              <h3>Caption</h3>
              <p>{show(selected.caption)}</p>
            </section>
            <section>
              <h3>Factors</h3>
              <Facts rows={experimentFacts(selected, { includeCopy: false })} />
            </section>
            <div className="actions">
              <button type="button" onClick={approve} disabled={Boolean(busy) || tooShort}>
                Approve
              </button>
              <button type="button" className="danger" onClick={reject} disabled={Boolean(busy)}>
                Reject
              </button>
            </div>
          </article>
        ) : null}
      </div>
    </>
  );
}

function Post({ experiments, selectedId, onSelect, onChanged }) {
  const ready = experiments.filter((row) => row.status === "approved" || row.status === "live");
  const selected = ready.find((row) => row.id === selectedId) || ready[0] || null;
  const [forms, setForms] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!selected?.id) return undefined;
    let cancelled = false;
    api(`/experiments/${encodeURIComponent(selected.id)}/publications`)
      .then((data) => {
        if (cancelled) return;
        const list = unwrapList(data);
        setForms((current) => {
          const existing = current[selected.id] || {
            tiktok: emptyPlatformRow(),
            instagram: emptyPlatformRow(),
            youtube: emptyPlatformRow(),
          };
          const next = { ...existing };
          for (const publication of list) {
            const platform = publication.platform;
            if (!next[platform]) continue;
            next[platform] = {
              ...next[platform],
              account_id: next[platform].account_id || publication.account_id || "",
              url: next[platform].url || publication.post_url || "",
              publication: next[platform].publication || publication,
            };
          }
          return { ...current, [selected.id]: next };
        });
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [selected?.id]);

  const formFor = forms[selected?.id] || {
    tiktok: emptyPlatformRow(),
    instagram: emptyPlatformRow(),
    youtube: emptyPlatformRow(),
  };

  function update(platform, patch) {
    setForms((current) => {
      const existing = current[selected.id] || {
        tiktok: emptyPlatformRow(),
        instagram: emptyPlatformRow(),
        youtube: emptyPlatformRow(),
      };
      return {
        ...current,
        [selected.id]: {
          ...existing,
          [platform]: { ...existing[platform], ...patch },
        },
      };
    });
  }

  async function send(platform) {
    if (!selected) return;
    const row = formFor[platform];
    if (!row.account_id.trim()) {
      setError("account_id is required.");
      return;
    }
    setBusy(platform);
    setError("");
    try {
      const data = await api(`/experiments/${encodeURIComponent(selected.id)}/publications`, {
        method: "POST",
        body: JSON.stringify({
          platform,
          account_id: row.account_id.trim(),
          token: row.token.trim() ? row.token : null,
        }),
      });
      const publication = publicationFrom(data);
      update(platform, { publication });
      if (publication?.status === "manual_needed") {
        await onChanged(`${platform} needs a manual post. Paste the URL after you publish it.`);
      } else {
        await onChanged(`${platform} publication is ${publication?.status || "sent"}.`);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function saveUrl(platform) {
    if (!selected) return;
    const row = formFor[platform];
    const publicationId = row.publication?.id || row.publication?.publication_id;
    if (!publicationId) {
      setError("This publication has no id yet.");
      return;
    }
    setBusy(`${platform}-url`);
    setError("");
    try {
      const data = await api(`/publications/${encodeURIComponent(publicationId)}/url`, {
        method: "POST",
        body: JSON.stringify({ url: row.url }),
      });
      const publication = publicationFrom(data) || { ...row.publication, post_url: row.url };
      update(platform, { publication });
      await onChanged(`Saved URL for ${platform}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function saveSnapshot(platform) {
    if (!selected) return;
    const row = formFor[platform];
    const publicationId = row.publication?.id || row.publication?.publication_id;
    if (!publicationId) {
      setError("Post this video before recording views.");
      return;
    }
    const views = Number(row.views);
    if (!Number.isFinite(views) || views < 0) {
      setError("Views must be zero or more.");
      return;
    }
    setBusy(`${platform}-views`);
    setError("");
    try {
      await api("/snapshots", {
        method: "POST",
        body: JSON.stringify({ publication_id: publicationId, views }),
      });
      await onChanged(`Recorded ${views} views for ${platform}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function completeSelected() {
    if (!selected) return;
    setBusy("complete");
    setError("");
    try {
      await api(`/experiments/${encodeURIComponent(selected.id)}/complete`, { method: "POST" });
      await onChanged(`Completed ${selected.id}. Suggest can use it.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <Banner>{error}</Banner>
      {ready.length === 0 ? <p>No approved or live experiment. Approve a cut in Review first.</p> : null}
      <div className="workspace">
        <ul className="picker">
          {ready.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                aria-pressed={selected?.id === row.id}
                onClick={() => onSelect(row.id)}
              >
                <span className="mono">{row.id}</span>
                <span className={`status status-${row.status}`}>{row.status}</span>
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <div>
            <p className="meta">
              <span className="mono">{selected.id}</span>
              <span className={`status status-${selected.status}`}>{selected.status}</span>
            </p>
            <p className="meta">Leave the token blank. This lab returns a manual pack instead of posting.</p>
            <ol className="platforms">
              {PLATFORMS.map((platform) => {
                const row = formFor[platform];
                const publication = row.publication;
                const manual = publication?.status === "manual_needed";
                return (
                  <li key={platform} className="panel">
                    <h2>{platform}</h2>
                    <div className="platform-fields">
                      <div className="filter">
                        <label htmlFor={`${selected.id}-${platform}-account`}>account_id</label>
                        <input
                          id={`${selected.id}-${platform}-account`}
                          type="text"
                          value={row.account_id}
                          onChange={(event) => update(platform, { account_id: event.target.value })}
                          autoComplete="off"
                          spellCheck={false}
                        />
                      </div>
                      <div className="filter">
                        <label htmlFor={`${selected.id}-${platform}-token`}>token</label>
                        <input
                          id={`${selected.id}-${platform}-token`}
                          type="password"
                          value={row.token}
                          onChange={(event) => update(platform, { token: event.target.value })}
                          autoComplete="off"
                          spellCheck={false}
                        />
                      </div>
                      <button type="button" onClick={() => send(platform)} disabled={Boolean(busy)}>
                        Send
                      </button>
                    </div>
                    {publication?.status ? (
                      <p className="meta">
                        publication status <span className="mono">{publication.status}</span>
                      </p>
                    ) : null}
                    {publication?.error ? <Banner>{publication.error}</Banner> : null}
                    {manual ? (
                      <div className="manual">
                        <p>
                          file path <code>{show(selected.file_path)}</code>
                        </p>
                        <p>caption</p>
                        <p>{show(selected.caption)}</p>
                        <div className="filter">
                          <label htmlFor={`${selected.id}-${platform}-url`}>URL</label>
                          <input
                            id={`${selected.id}-${platform}-url`}
                            type="url"
                            value={row.url}
                            onChange={(event) => update(platform, { url: event.target.value })}
                            spellCheck={false}
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => saveUrl(platform)}
                          disabled={busy === `${platform}-url`}
                        >
                          Save URL
                        </button>
                      </div>
                    ) : null}
                    {publication?.status === "posted" ? (
                      <div className="manual">
                        <div className="filter">
                          <label htmlFor={`${selected.id}-${platform}-views`}>views</label>
                          <input
                            id={`${selected.id}-${platform}-views`}
                            type="number"
                            min="0"
                            value={row.views}
                            onChange={(event) => update(platform, { views: event.target.value })}
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => saveSnapshot(platform)}
                          disabled={busy === `${platform}-views`}
                        >
                          Record views
                        </button>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ol>
            {selected.status === "live" ? (
              <div className="actions">
                <button type="button" onClick={completeSelected} disabled={busy === "complete"}>
                  Complete experiment
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </>
  );
}

function Results() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api("/results")
      .then((data) => {
        if (!cancelled) setRows(unwrapList(data));
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <Banner>{error}</Banner>
      {loaded && rows.length === 0 && !error ? <p>No results yet.</p> : null}
      <div className="score">
        {rows.map((row, index) => {
          const views = viewsOf(row);
          const title = [row.niche_id, styleKind(row), moneyKind(row)].filter(Boolean).join(" · ");
          const below =
            row.status === "complete" &&
            (row.below_sample_floor === true || row.below_sample_floor === "true");
          return (
            <article key={row.id || `${title}-${index}`} className="panel">
              <h2>{title || row.id || "Cell"}</h2>
              <dl className="facts">
                <div>
                  <dt>revenue_cents</dt>
                  <dd>{show(row.revenue_cents)}</dd>
                </div>
                <div>
                  <dt>clicks</dt>
                  <dd>{show(row.clicks)}</dd>
                </div>
                {views !== undefined ? (
                  <div>
                    <dt>views</dt>
                    <dd>{show(views)}</dd>
                  </div>
                ) : null}
              </dl>
              {below ? <p className="floor">Fewer than 3 completed videos in this cell.</p> : null}
            </article>
          );
        })}
      </div>
    </>
  );
}

function Proposals({ drafts, setDrafts, onAccepted }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function suggest() {
    setBusy("suggest");
    setError("");
    try {
      const data = await api("/suggest", { method: "POST" });
      setDrafts(unwrapList(data));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function acceptDraft(index) {
    const draft = drafts[index];
    if (!draft) return;
    setBusy(`accept-${index}`);
    setError("");
    try {
      await api("/experiments", {
        method: "POST",
        body: JSON.stringify(draftPayload(draft)),
      });
      setDrafts((current) => current.filter((_item, position) => position !== index));
      await onAccepted(`Accepted draft ${index + 1}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  function discardDraft(index) {
    setError("");
    setDrafts((current) => current.filter((_item, position) => position !== index));
  }

  return (
    <>
      <Banner>{error}</Banner>
      <p>The model writes the next draft from completed videos.</p>
      <div className="actions">
        <button type="button" onClick={suggest} disabled={busy === "suggest"}>
          Suggest
        </button>
      </div>
      {drafts.length === 0 ? <p className="meta">No drafts yet. Suggest to ask for one.</p> : null}
      <div className="stack">
        {drafts.map((draft, index) => {
          const diffs = Array.isArray(draft.factor_diffs) ? draft.factor_diffs : [];
          return (
            <article key={`${draft.niche_id || "draft"}-${draft.hook_id || index}-${index}`} className="panel">
              <h2>
                Draft {index + 1}
                {draft.niche_id ? ` · ${draft.niche_id}` : ""}
              </h2>
              <table>
                <caption>factor_diffs</caption>
                <thead>
                  <tr>
                    <th scope="col">field</th>
                    <th scope="col">parent_value</th>
                    <th scope="col">next_value</th>
                  </tr>
                </thead>
                <tbody>
                  {diffs.length === 0 ? (
                    <tr>
                      <td colSpan={3}>No factor diffs on this draft.</td>
                    </tr>
                  ) : (
                    diffs.map((diff, diffIndex) => (
                      <tr key={`${diff.field || "field"}-${diffIndex}`}>
                        <td>{show(diff.field)}</td>
                        <td>{show(diff.parent_value)}</td>
                        <td>{show(diff.next_value)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
              <Facts
                rows={[
                  { label: "hook_id", value: show(draft.hook_id) },
                  { label: "style.kind", value: show(styleKind(draft)) },
                  { label: "money.kind", value: show(moneyKind(draft)) },
                  { label: "hypothesis", value: show(draft.hypothesis), wide: true },
                  { label: "script", value: show(draft.script), wide: true },
                  {
                    label: "beats",
                    value: Array.isArray(draft.beats)
                      ? draft.beats.map((beat) => beat.spoken).filter(Boolean).join(" / ")
                      : "—",
                    wide: true,
                  },
                  { label: "caption", value: show(draft.caption), wide: true },
                ]}
              />
              <div className="actions">
                <button
                  type="button"
                  onClick={() => acceptDraft(index)}
                  disabled={Boolean(busy)}
                >
                  {busy === `accept-${index}` ? "Accepting…" : "Accept"}
                </button>
                <button
                  type="button"
                  className="danger"
                  onClick={() => discardDraft(index)}
                  disabled={Boolean(busy)}
                >
                  Discard
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}

function Catalog({ onBuilt }) {
  const [hints, setHints] = useState({ themes: [], niches: [], voices: [], presenters: [], hooks: [] });
  const [renderCap, setRenderCap] = useState(8);
  const [catalogMissing, setCatalogMissing] = useState(false);
  const [draftLength, setDraftLength] = useState(45);
  const [themeId, setThemeId] = useState("");
  const [nicheIds, setNicheIds] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [presenterId, setPresenterId] = useState("");
  const [hookId, setHookId] = useState("");
  const [kind, setKind] = useState("platform_payout");
  const [platform, setPlatform] = useState("tiktok");
  const [trackingCode, setTrackingCode] = useState("");
  const [merchant, setMerchant] = useState("");
  const [offerUrl, setOfferUrl] = useState("");
  const [created, setCreated] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function loadCatalog() {
    try {
      const data = await api("/catalog");
      setHints(normalizeCatalog(data));
      setRenderCap(Number(data.render_cap) || 8);
      setCatalogMissing(false);
    } catch (err) {
      if (err.status === 404) {
        setCatalogMissing(true);
        return;
      }
      setError(errorMessage(err));
    }
  }

  useEffect(() => {
    loadCatalog();
  }, []);

  const starterSeconds = kind === "platform_payout" && platform === "tiktok" ? 75 : 45;

  useEffect(() => {
    setDraftLength(starterSeconds);
  }, [starterSeconds]);

  function money() {
    return moneyPayload(kind, platform, trackingCode, merchant, offerUrl);
  }

  function moneyError() {
    if (kind === "affiliate" && (!trackingCode.trim() || !merchant.trim())) {
      return "Affiliate drafts need a tracking code and a merchant.";
    }
    if (kind === "own_offer" && (!trackingCode.trim() || !offerUrl.trim())) {
      return "An own offer needs a tracking code and an offer URL.";
    }
    return "";
  }

  async function buildStarter(event) {
    event.preventDefault();
    const niches = splitIds(nicheIds);
    if (niches.length === 0 || !voiceId.trim() || !presenterId.trim() || !hookId.trim()) {
      setError("Niche, voice, presenter, and hook are required. The grid writes both styles.");
      return;
    }
    const invalidMoney = moneyError();
    if (invalidMoney) {
      setError(invalidMoney);
      return;
    }
    setBusy("starter");
    setError("");
    try {
      const data = await api("/starter", {
        method: "POST",
        body: JSON.stringify({
          niche_ids: splitIds(nicheIds),
          money: money(),
          hook_id: hookId.trim(),
          voice_id: voiceId.trim(),
          presenter_id: presenterId.trim(),
        }),
      });
      const list = unwrapList(data);
      setCreated(list);
      await onBuilt(`Starter grid returned ${list.length}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function addTheme() {
    const id = themeId.trim();
    if (!id) {
      setError("Enter a theme id.");
      return;
    }
    setBusy("theme");
    setError("");
    try {
      await api("/themes", {
        method: "POST",
        body: JSON.stringify({ id, name: id, language: "en" }),
      });
      await loadCatalog();
      await onBuilt(`Saved theme ${id}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function addNiche() {
    const theme = themeId.trim();
    const niches = splitIds(nicheIds);
    if (!theme || niches.length === 0) {
      setError("Enter a theme id and a niche id.");
      return;
    }
    setBusy("niche");
    setError("");
    try {
      for (const nicheId of niches) {
        await api("/niches", {
          method: "POST",
          body: JSON.stringify({ id: nicheId, theme_id: theme, name: nicheId }),
        });
      }
      await loadCatalog();
      await onBuilt(`Saved ${niches.length} niche${niches.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  async function saveExperimentDraft() {
    const niches = splitIds(nicheIds);
    if (niches.length === 0 || !hookId.trim() || !voiceId.trim()) {
      setError("Niche, voice, and hook are required.");
      return;
    }
    const length = Number(draftLength);
    if (!Number.isInteger(length) || length <= 0) {
      setError("Length must be a whole number of seconds.");
      return;
    }
    if (kind === "platform_payout" && platform === "tiktok" && length <= 60) {
      setError(TIKTOK_LENGTH);
      return;
    }
    const invalidMoney = moneyError();
    if (invalidMoney) {
      setError(invalidMoney);
      return;
    }
    setBusy("draft");
    setError("");
    try {
      const saved = [];
      for (const nicheId of niches) {
        const data = await api("/experiments", {
          method: "POST",
          body: JSON.stringify({
            niche_id: nicheId,
            hook_id: hookId.trim(),
            hypothesis: `Compare styles in ${nicheId}`,
            script: `Draft script for ${nicheId}.`,
            caption: `Draft caption for ${nicheId}.`,
            length_sec: length,
            style: styleFromForm(voiceId, presenterId),
            money: money(),
          }),
        });
        saved.push(data);
      }
      setCreated(unwrapList(saved.length === 1 ? saved[0] : saved));
      await onBuilt(`Saved ${niches.length} experiment draft${niches.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <Banner>{error}</Banner>
      <p className="cap">
        Daily render cap is <strong>{renderCap}</strong>. The starter grid writes drafts only, at{" "}
        <strong>{starterSeconds}</strong> seconds.
      </p>
      {kind === "platform_payout" && platform === "tiktok" ? (
        <p>TikTok Creator Rewards needs a video longer than 60 seconds, so these drafts are 75 seconds.</p>
      ) : null}
      {catalogMissing ? (
        <p>No catalog route. Niche, voice, presenter, and hook stay text fields on this form.</p>
      ) : null}
      <form onSubmit={buildStarter} className="stack">
        <fieldset>
          <legend>Starter</legend>
          <div className="form-grid">
            <div className="filter">
              <label htmlFor="theme-id">Theme id</label>
              <input
                id="theme-id"
                type="text"
                value={themeId}
                onChange={(event) => setThemeId(event.target.value)}
                list="catalog-themes"
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                placeholder="history"
              />
              <datalist id="catalog-themes">
                {hints.themes.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>
            </div>
            <div className="filter">
              <label htmlFor="niche-id">Niche id</label>
              <input
                id="niche-id"
                type="text"
                value={nicheIds}
                onChange={(event) => setNicheIds(event.target.value)}
                list="catalog-niches"
                spellCheck={false}
                placeholder="niche-a, niche-b"
              />
              <datalist id="catalog-niches">
                {hints.niches.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>
            </div>
            <div className="filter">
              <label htmlFor="voice-id">Voice id</label>
              <input
                id="voice-id"
                type="text"
                value={voiceId}
                onChange={(event) => setVoiceId(event.target.value)}
                list="catalog-voices"
                spellCheck={false}
              />
              <datalist id="catalog-voices">
                {hints.voices.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>
            </div>
            <div className="filter">
              <label htmlFor="presenter-id">Presenter id</label>
              <input
                id="presenter-id"
                type="text"
                value={presenterId}
                onChange={(event) => setPresenterId(event.target.value)}
                list="catalog-presenters"
                spellCheck={false}
              />
              <datalist id="catalog-presenters">
                {hints.presenters.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>
            </div>
            <div className="filter">
              <label htmlFor="hook-id">Hook id</label>
              <input
                id="hook-id"
                type="text"
                value={hookId}
                onChange={(event) => setHookId(event.target.value)}
                list="catalog-hooks"
                spellCheck={false}
              />
              <datalist id="catalog-hooks">
                {hints.hooks.map((id) => (
                  <option key={id} value={id} />
                ))}
              </datalist>
            </div>
          </div>
        </fieldset>
        <fieldset>
          <legend>Money</legend>
          <div className="form-grid">
            <div className="filter">
              <label htmlFor="money-kind">money.kind</label>
              <select id="money-kind" value={kind} onChange={(event) => setKind(event.target.value)}>
                {MONEY_KINDS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            {kind === "platform_payout" ? (
              <div className="filter">
                <label htmlFor="money-platform">platform</label>
                <select
                  id="money-platform"
                  value={platform}
                  onChange={(event) => setPlatform(event.target.value)}
                >
                  {PLATFORMS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            {kind !== "platform_payout" ? (
              <div className="filter">
                <label htmlFor="tracking-code">tracking_code</label>
                <input
                  id="tracking-code"
                  type="text"
                  value={trackingCode}
                  onChange={(event) => setTrackingCode(event.target.value)}
                  spellCheck={false}
                />
              </div>
            ) : null}
            {kind === "affiliate" ? (
              <div className="filter">
                <label htmlFor="merchant">merchant</label>
                <input
                  id="merchant"
                  type="text"
                  value={merchant}
                  onChange={(event) => setMerchant(event.target.value)}
                  spellCheck={false}
                />
              </div>
            ) : null}
            {kind === "own_offer" ? (
              <div className="filter">
                <label htmlFor="offer-url">offer_url</label>
                <input
                  id="offer-url"
                  type="url"
                  value={offerUrl}
                  onChange={(event) => setOfferUrl(event.target.value)}
                />
              </div>
            ) : null}
          </div>
        </fieldset>
        <div className="filter">
          <label htmlFor="draft-length">Draft length in seconds</label>
          <input
            id="draft-length"
            type="number"
            min="1"
            value={draftLength}
            onChange={(event) => setDraftLength(event.target.value)}
          />
        </div>
        <div className="actions">
          <button type="button" onClick={addTheme} disabled={Boolean(busy)}>
            Add theme
          </button>
          <button type="button" onClick={addNiche} disabled={Boolean(busy)}>
            Add niche
          </button>
          <button type="submit" disabled={busy === "starter"}>
            Build starter grid
          </button>
          <button type="button" onClick={saveExperimentDraft} disabled={busy === "draft"}>
            Save experiment draft
          </button>
        </div>
        <p className="meta">
          Save experiment draft uses the length above. Build starter grid always writes both styles at{" "}
          {starterSeconds} seconds.
        </p>
      </form>
      {created.length > 0 ? (
        <section>
          <h2>Returned</h2>
          <ul className="plain">
            {created.map((row, index) => (
              <li key={row.id || index}>
                <span className="mono">{row.id || `item ${index + 1}`}</span>
                {" · "}
                {show(row.niche_id)}
                {" · "}
                {show(styleKind(row) || row.status)}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

export default function App() {
  const [screen, setScreen] = useState("Board");
  const [experiments, setExperiments] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [notice, setNotice] = useState("");
  const [drafts, setDrafts] = useState([]);

  async function loadExperiments() {
    try {
      const data = await api("/experiments");
      const list = unwrapList(data);
      setExperiments(list);
      setLoadError("");
      setSelectedId((current) => {
        if (current && list.some((row) => row.id === current)) return current;
        return list[0]?.id || "";
      });
    } catch (error) {
      setLoadError(errorMessage(error));
    }
  }

  useEffect(() => {
    loadExperiments();
  }, []);

  return (
    <div className="app">
      <a className="skip" href="#main">
        Skip to screen
      </a>
      <header className="topbar">
        <p className="mark">Dead Internet</p>
        <p className="mark-sub">Short-video lab</p>
      </header>
      <nav className="rail" aria-label="Screens">
        <ul>
          {SCREENS.map((name) => (
            <li key={name}>
              <button
                type="button"
                aria-current={screen === name ? "page" : undefined}
                onClick={() => {
                  setScreen(name);
                  setNotice("");
                }}
              >
                {name}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <main id="main">
        <h1>{screen}</h1>
        <Banner tone="ok">{notice}</Banner>
        {screen === "Board" ? (
          <Board
            experiments={experiments}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onRefresh={loadExperiments}
            onChanged={async (message) => {
              setNotice(message);
              await loadExperiments();
            }}
            error={loadError}
          />
        ) : null}
        {screen === "Review" ? (
          <Review
            experiments={experiments}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onChanged={async (message) => {
              setNotice(message);
              await loadExperiments();
            }}
          />
        ) : null}
        {screen === "Post" ? (
          <Post
            experiments={experiments}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onChanged={async (message) => {
              setNotice(message);
              await loadExperiments();
            }}
          />
        ) : null}
        {screen === "Results" ? <Results /> : null}
        {screen === "Proposals" ? (
          <Proposals
            drafts={drafts}
            setDrafts={setDrafts}
            onAccepted={async (message) => {
              setNotice(message);
              await loadExperiments();
            }}
          />
        ) : null}
        {screen === "Catalog" ? (
          <Catalog
            onBuilt={async (message) => {
              setNotice(message);
              await loadExperiments();
            }}
          />
        ) : null}
      </main>
    </div>
  );
}
