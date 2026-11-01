import { useEffect, useMemo, useState } from "react";

const SCREENS = ["Board", "Review", "Post", "Results", "Proposals", "Catalog"];
const PLATFORMS = ["tiktok", "instagram", "youtube"];
const STATUSES = [
  "draft",
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

function videoSrc(filePath) {
  if (typeof filePath !== "string") return "";
  const trimmed = filePath.trim();
  if (!trimmed || /^javascript:/i.test(trimmed)) return "";
  return trimmed;
}

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
  };
}

function publicationFrom(data) {
  if (!data || typeof data !== "object") return null;
  if (data.publication && typeof data.publication === "object") return data.publication;
  return data;
}

function emptyPlatformRow() {
  return { account_id: "", token: "", url: "", publication: null };
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

function experimentFacts(experiment, { includeCopy = true } = {}) {
  const style = experiment.style && typeof experiment.style === "object" ? experiment.style : {};
  const money = experiment.money && typeof experiment.money === "object" ? experiment.money : {};
  const rows = [
    { label: "id", value: show(experiment.id) },
    { label: "status", value: show(experiment.status) },
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

function Board({ experiments, selectedId, onSelect, onRefresh, error }) {
  const [niche, setNiche] = useState("");
  const [style, setStyle] = useState("");
  const [money, setMoney] = useState("");
  const [status, setStatus] = useState("");

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
          {selected ? <Facts rows={experimentFacts(selected)} /> : <p>Select a row.</p>}
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
  const src = videoSrc(selected?.file_path);

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
      {queue.length === 0 ? <p>Nothing is in review.</p> : null}
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
              {src ? (
                <video controls width="270" height="480" src={src} playsInline />
              ) : (
                <p>No rendered file yet.</p>
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
              <button type="button" onClick={approve} disabled={Boolean(busy)}>
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
    setBusy(platform);
    setError("");
    try {
      const data = await api(`/experiments/${encodeURIComponent(selected.id)}/publications`, {
        method: "POST",
        body: JSON.stringify({
          platform,
          account_id: row.account_id,
          token: row.token,
        }),
      });
      const publication = publicationFrom(data);
      update(platform, { publication });
      if (publication?.status !== "manual_needed") {
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

  return (
    <>
      <Banner>{error}</Banner>
      {ready.length === 0 ? <p>No approved or live experiment.</p> : null}
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
                          type="text"
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
                  </li>
                );
              })}
            </ol>
          </div>
        ) : null}
      </div>
    </>
  );
}

function Results() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api("/results")
      .then((data) => {
        if (!cancelled) setRows(unwrapList(data));
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <Banner>{error}</Banner>
      {rows.length === 0 && !error ? <p>No results yet.</p> : null}
      <div className="score">
        {rows.map((row, index) => {
          const views = viewsOf(row);
          const title = [row.niche_id, styleKind(row), moneyKind(row)].filter(Boolean).join(" · ");
          const below = row.below_sample_floor === true || row.below_sample_floor === "true";
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

  async function acceptDrafts() {
    if (drafts.length === 0) {
      setError("Suggest first. There are no drafts to accept.");
      return;
    }
    setBusy("accept");
    setError("");
    try {
      for (const draft of drafts) {
        await api("/experiments", {
          method: "POST",
          body: JSON.stringify(draftPayload(draft)),
        });
      }
      const count = drafts.length;
      setDrafts([]);
      await onAccepted(`Accepted ${count} draft${count === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <Banner>{error}</Banner>
      <p>Suggest reads completed videos and lists the next factor changes.</p>
      <div className="actions">
        <button type="button" onClick={suggest} disabled={busy === "suggest"}>
          Suggest
        </button>
        <button type="button" onClick={acceptDrafts} disabled={busy === "accept"}>
          Accept drafts
        </button>
      </div>
      {drafts.length === 0 ? <p className="meta">No drafts yet.</p> : null}
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
                  { label: "caption", value: show(draft.caption), wide: true },
                ]}
              />
            </article>
          );
        })}
      </div>
    </>
  );
}

function Catalog({ onBuilt }) {
  const [hints, setHints] = useState({ niches: [], voices: [], presenters: [], hooks: [] });
  const [catalogMissing, setCatalogMissing] = useState(false);
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

  useEffect(() => {
    let cancelled = false;
    api("/catalog")
      .then((data) => {
        if (cancelled) return;
        setHints(normalizeCatalog(data));
        setCatalogMissing(false);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err.status === 404) {
          setCatalogMissing(true);
          return;
        }
        setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function money() {
    return moneyPayload(kind, platform, trackingCode, merchant, offerUrl);
  }

  async function buildStarter(event) {
    event.preventDefault();
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

  async function saveExperimentDraft() {
    const niches = splitIds(nicheIds);
    if (niches.length === 0) {
      setError("Enter a niche id.");
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
            length_sec: 45,
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
        Daily render cap is <strong>8</strong>. The starter grid writes drafts only.
      </p>
      {catalogMissing ? (
        <p>No catalog route. Niche, voice, presenter, and hook stay text fields on this form.</p>
      ) : null}
      <form onSubmit={buildStarter} className="stack">
        <fieldset>
          <legend>Starter</legend>
          <div className="form-grid">
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
        <div className="actions">
          <button type="submit" disabled={busy === "starter"}>
            Build starter grid
          </button>
          {catalogMissing ? (
            <button type="button" onClick={saveExperimentDraft} disabled={busy === "draft"}>
              Save experiment draft
            </button>
          ) : null}
        </div>
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
                onClick={() => setScreen(name)}
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
