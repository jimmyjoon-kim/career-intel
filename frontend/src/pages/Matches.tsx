import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Empty, ErrorBox, useFetch } from "../components";

type ProfileItem = { tag: string; label: string; share: number; match: number; closable: boolean };
type RoleType = {
  id: string; cluster: string; vertical: string; title: string; n_open: number; n_gate_pass: number; companies: string[];
  fit: number | null; profile: ProfileItem[]; met: string[]; unmet: string[]; typical_level: string | null;
  level_relation: string; level_mix: Record<string, number>; median_pay_mid: number | null; pay_n: number;
  opportunity_median: number | null; domain_evidence: number | null; posting_ids: number[];
  holders: { n: number; position: number; median: number; your_score: number } | null;
};
type Position = {
  id: number; company: string; title: string; url: string; location: string; level_band: string; vertical: string;
  cluster: string; pay_range: string; requirement_match: number; rank_score: number; hard_gaps: string[]; gaps: string[];
  opportunity: number | null; level_relation: string;
};
type Worth = {
  id: number; company: string; title: string; url: string; location: string; level_band: string; status: string;
  requirement_match: number; outside: string[]; hard_gaps: string[]; gaps: string[]; level_note: string; level_evidence: string[];
};
type Matches = {
  progression: { established: number | null; established_label: string | null; established_months: number; recent_label: string | null };
  role_types: RoleType[]; positions: Position[]; worth_a_look?: Worth[]; method: string[];
};
type Found = { company: string; title: string; location: string; url: string; source: string; why: string; seen_in_search: boolean; status: string };
type SearchOut = { available: boolean; results: Found[]; note: string };
type Detail = { kind: "type"; t: RoleType } | { kind: "pos"; p: Position } | { kind: "method" };

const money = (v: number | null) => (v ? `$${Math.round(v / 1000)}k` : "—");
const relCls = (r: string) => (r === "above your level" ? "warn" : r === "at your level" ? "good" : "acc");

export default function MatchesPage() {
  const { data, error, loading } = useFetch<Matches>("/api/matches");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState<SearchOut | null>(null);
  const [serr, setSerr] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setDetail(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const runSearch = async (query: string) => {
    setQ(query); setBusy(true); setSerr(null); setDetail(null);
    try { setFound(await api<SearchOut>("/api/matches/search", { method: "POST", json: { query } })); }
    catch (e) { setSerr((e as Error).message); } finally { setBusy(false); }
  };

  if (loading && !data) return <div className="muted">Loading…</div>;
  if (!data) return <ErrorBox msg={error} />;
  const pr = data.progression;

  return (
    <div className="sc">
      <header className="tile-head" style={{ alignItems: "flex-end" }}>
        <div>
          <span className="kick" style={{ color: "var(--muted)" }}>Built from open postings and your record</span>
          <h1 style={{ margin: "4px 0 0" }}>Job matches</h1>
        </div>
        <button className="more-link" onClick={() => setDetail({ kind: "method" })}>How matches are found ›</button>
      </header>

      <section className="sc-row3">
        <div className="tile">
          <span className="kick acc">Career progression</span>
          <div className="big" style={{ margin: "8px 0" }}>{pr.established_label ?? "—"}</div>
          <div className="small" style={{ color: "var(--ink-2)" }}>Level held longest in the last 10 years ({pr.established_months} months). Most recent: {pr.recent_label ?? "—"}.</div>
        </div>
        <div className="tile">
          <span className="kick good">Best-fit role type</span>
          <div style={{ fontSize: 18, fontWeight: 700, margin: "8px 0" }}>{data.role_types[0]?.title ?? "—"}</div>
          <div className="small" style={{ color: "var(--ink-2)" }}>{data.role_types[0] ? `${data.role_types[0].fit}% fit · ${data.role_types[0].n_open} open postings` : ""}</div>
        </div>
        <div className="tile">
          <span className="kick warn">Ranked open positions</span>
          <div className="big" style={{ margin: "8px 0" }}>{data.positions.length}</div>
          <div className="small" style={{ color: "var(--ink-2)" }}>Pass your gate. {data.positions.filter((p) => !p.hard_gaps.length).length} with no missing minimum.</div>
        </div>
      </section>

      <section className="tile">
        <div className="tile-head">
          <span className="tile-title">Role types by industry</span>
          <span className="small muted">Fit = how well your record covers what these postings ask for. Select one for its requirements and postings.</span>
        </div>
        {data.role_types.length === 0 ? <Empty>No role types yet: at least two open postings per group are needed.</Empty> : (
          <div className="types">
            {data.role_types.map((t) => (
              <button key={t.id} className="hit type-card" onClick={() => setDetail({ kind: "type", t })}>
                <div className="type-top">
                  <span><span className="kick acc">{t.vertical}</span><b style={{ fontSize: 16 }}>{t.cluster}</b></span>
                  <Ring v={t.fit ?? 0} />
                </div>
                <div className="small" style={{ color: "var(--ink-2)" }}>{t.n_open} open · {t.companies.slice(0, 3).join(", ")}{t.companies.length > 3 ? "…" : ""}</div>
                <div className="chips">
                  <span className={`chip-d ${relCls(t.level_relation)}`}>{t.typical_level} · {t.level_relation}</span>
                  {t.median_pay_mid && <span className="chip-d">{money(t.median_pay_mid)} mid</span>}
                  {t.holders && <span className="chip-d good">you: {Math.round(t.holders.position)}th among holders</span>}
                </div>
                {t.unmet.length > 0 && <div className="small muted">Missing: {t.unmet.slice(0, 2).join(", ")}</div>}
              </button>
            ))}
          </div>
        )}
      </section>

      {(data.worth_a_look?.length ?? 0) > 0 && (
        <section className="tile" style={{ marginBottom: 16 }}>
          <div className="tile-head"><span className="tile-title">Worth a look: outside your stated criteria, strong fit on your CV</span></div>
          <p className="small muted" style={{ marginTop: 0 }}>Each misses only a preference you set (shown in amber). Levels are read from the posting's description, not its title.</p>
          {data.worth_a_look!.map((w) => (
            <div key={w.id} className="prop">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span><b>{w.company}</b> — {w.title} <span className="small muted">· {w.location} · {w.level_band}</span>{" "}
                  <a className="small" href={w.url} target="_blank" rel="noreferrer">posting</a></span>
                <b>{Math.round(w.requirement_match)}%</b>
              </div>
              <div className="chips" style={{ marginTop: 4 }}>
                {w.outside.map((o) => <span key={o} className="chip-d warn">{o}</span>)}
                {w.hard_gaps.map((g) => <span key={g} className="chip-d">missing: {g}</span>)}
              </div>
              {w.level_note && <div className="small" style={{ marginTop: 4 }}>{w.level_note}</div>}
              {w.level_evidence.length > 0 && <details className="small"><summary>Level evidence from the posting</summary>
                <ul>{w.level_evidence.map((q, i) => <li key={i}>“{q}”</li>)}</ul></details>}
            </div>
          ))}
        </section>
      )}

      <section className="sc-row2">
        <div className="tile">
          <div className="tile-head"><span className="tile-title">Open positions ranked for you</span><Link className="more-link" to="/postings">All postings →</Link></div>
          {data.positions.map((p) => (
            <button key={p.id} className="hit rank-row" onClick={() => setDetail({ kind: "pos", p })}>
              <span><b>{p.company}</b><br /><span className="small muted">{p.title}</span></span>
              <span className="track"><span className="fill" style={{ width: `${p.requirement_match}%`, background: p.hard_gaps.length ? "var(--bad)" : undefined }} /></span>
              <b>{Math.round(p.requirement_match)}%</b>
            </button>
          ))}
        </div>
        <div className="tile">
          <div className="tile-title">Search for more open positions</div>
          <p className="small muted" style={{ margin: "4px 0 12px" }}>Live web search, company careers pages first. Uses your profile and gate. Results are not yet checked against each company's live board.</p>
          <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 3) runSearch(q.trim()); }} style={{ display: "flex", gap: 8 }}>
            <label style={{ flex: 1, margin: 0 }}><span className="sr-only">Search query</span>
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Head of Partnerships, AI platform, Bay Area" />
            </label>
            <button className="btn primary" disabled={busy || q.trim().length < 3}>{busy ? "Searching…" : "Search"}</button>
          </form>
          <div className="chips" style={{ marginTop: 10 }}>
            {data.role_types.slice(0, 3).map((t) => (
              <button key={t.id} className="chip-btn" onClick={() => runSearch(`Director+ ${t.cluster} roles in ${t.vertical}, US or Bay Area`)}>{t.title}</button>
            ))}
          </div>
          <ErrorBox msg={serr} />
          {found && (
            <div style={{ marginTop: 12 }}>
              <p className="small muted">{found.note}</p>
              {found.results.length === 0 ? <p className="small muted">No results.</p> : (
                <ul className="ev">{found.results.map((r, i) => (
                  <li key={i}>
                    <div className="src">{r.source}{r.seen_in_search ? " · link seen in search results" : " · link not confirmed in search results"}</div>
                    <a href={r.url} target="_blank" rel="noreferrer"><b>{r.company}</b> · {r.title}</a>
                    <div className="small muted">{r.location}</div>
                    <div className="small">{r.why}</div>
                  </li>
                ))}</ul>
              )}
            </div>
          )}
        </div>
      </section>

      {detail && (
        <div className="panel-wrap" onClick={() => setDetail(null)}>
          <aside className="panel" role="dialog" aria-modal="true" aria-label="Details" onClick={(e) => e.stopPropagation()}>
            <div className="panel-top"><span className="kick" style={{ color: "var(--muted)" }}>Detail</span><button className="x" onClick={() => setDetail(null)} aria-label="Close details">×</button></div>
            {detail.kind === "type" && <TypeDetail t={detail.t} positions={data.positions} onSearch={runSearch} />}
            {detail.kind === "pos" && <PosDetail p={detail.p} />}
            {detail.kind === "method" && (<><h2>How matches are found</h2><ul className="ev">{data.method.map((m) => <li key={m}>{m}</li>)}</ul>
              <p className="small muted">Requirement evidence comes from your experience text, CV and Role review. Change anything that is wrong on Role review or Profile.</p></>)}
          </aside>
        </div>
      )}
    </div>
  );
}

function Ring({ v }: { v: number }) {
  const r = 22, c = 2 * Math.PI * r;
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" role="img" aria-label={`${v}% fit`}>
      <circle cx="28" cy="28" r={r} fill="none" stroke="var(--line)" strokeWidth="6" />
      <circle cx="28" cy="28" r={r} fill="none" stroke="var(--accent-strong)" strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${(c * v) / 100} ${c}`} transform="rotate(-90 28 28)" />
      <text x="28" y="32" textAnchor="middle" fontSize="13" fontWeight="800" className="svg-ink">{Math.round(v)}</text>
    </svg>
  );
}

function TypeDetail({ t, positions, onSearch }: { t: RoleType; positions: Position[]; onSearch: (q: string) => void }) {
  const mine = positions.filter((p) => t.posting_ids.includes(p.id));
  return (<>
    <span className="kick acc">{t.vertical}</span><h2>{t.cluster}</h2>
    <dl className="kv">
      <dt>Fit</dt><dd>{t.fit}% of what these postings ask for</dd>
      <dt>Open postings</dt><dd>{t.n_open} ({t.n_gate_pass} pass your gate)</dd>
      <dt>Companies</dt><dd>{t.companies.join(", ")}</dd>
      <dt>Typical level</dt><dd>{t.typical_level} · {t.level_relation} · mix {Object.entries(t.level_mix).map(([k, v]) => `${k} ${v}`).join(", ")}</dd>
      <dt>Pay midpoint</dt><dd>{money(t.median_pay_mid)} (median of {t.pay_n} stated ranges)</dd>
      <dt>Opportunity score</dt><dd>{t.opportunity_median ?? "—"} median across these postings</dd>
    </dl>
    {t.holders ? (
      <div className="callout good">Competitive read: you rank {Math.round(t.holders.position)}th percentile among {t.holders.n} people recently hired into {t.cluster} roles (your score {t.holders.your_score}, their median {t.holders.median}).</div>
    ) : (
      <div className="callout">No role-holder data for {t.cluster} roles yet; only Partnerships holders have been collected. Peer comparison for this role type will appear once its hires are read.</div>
    )}
    <h3>What these postings ask for</h3>
    {t.profile.map((x) => (
      <div key={x.tag} className="fac" style={{ cursor: "inherit", gridTemplateColumns: "minmax(0,1.4fr) minmax(0,1fr) 72px" }}>
        <span>{x.label}</span>
        <span className="track"><span className="fill" style={{ width: `${100 * x.share}%`, background: x.match >= 1 ? undefined : x.match > 0 ? "var(--dim)" : "var(--bad)" }} /></span>
        <span className="gapv small">{Math.round(100 * x.share)}% · {x.match >= 1 ? "Has" : x.match > 0 ? "Partial" : "No"}</span>
      </div>
    ))}
    <div className="small muted">Bar = share of postings asking for it; colour = your evidence (blue has, dim partial, red missing).</div>
    {mine.length > 0 && (<><h3>Postings in this group that pass your gate</h3>
      <ul className="ev">{mine.map((p) => <li key={p.id}><a href={p.url} target="_blank" rel="noreferrer"><b>{p.company}</b> · {p.title}</a><div className="small muted">{Math.round(p.requirement_match)}% requirement match · {p.location}</div></li>)}</ul></>)}
    <button className="btn primary" onClick={() => onSearch(`Director+ ${t.cluster} roles in ${t.vertical}, US or Bay Area`)}>Search the web for more like this</button>
  </>);
}

function PosDetail({ p }: { p: Position }) {
  return (<>
    <span className="kick acc">{p.company} · {p.vertical}</span><h2>{p.title}</h2>
    <dl className="kv">
      <dt>Requirement match</dt><dd>{p.requirement_match}%</dd>
      <dt>Opportunity score</dt><dd>{p.opportunity ?? "—"}</dd>
      <dt>Level</dt><dd>{p.level_band} · {p.level_relation}</dd>
      <dt>Cluster</dt><dd>{p.cluster}</dd><dt>Location</dt><dd>{p.location}</dd><dt>Pay</dt><dd>{p.pay_range || "Not stated"}</dd>
    </dl>
    {p.hard_gaps.length > 0 && <div className="callout">Missing minimum: {p.hard_gaps.join(", ")}</div>}
    {p.gaps.length > 0 && (<><h3>Requirements not fully met</h3><ul className="ev">{p.gaps.map((g) => <li key={g}>{g}</li>)}</ul></>)}
    <a className="more-link" href={p.url} target="_blank" rel="noreferrer">Open posting ↗</a>
  </>);
}
