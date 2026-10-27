import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Card, Factor, RoleRead, Row, Scorecard } from "../api";
import { Empty, ErrorBox, useFetch } from "../components";

type Reading = NonNullable<Scorecard["reading"]>;
type Peer = Card["peers"][number];
type Detail =
  | { kind: "score" }
  | { kind: "position" }
  | { kind: "factor"; f: Factor }
  | { kind: "focus" }
  | { kind: "rare" }
  | { kind: "cell"; role: RoleRead; tag: string }
  | { kind: "role"; role: RoleRead }
  | { kind: "posting"; row: Row }
  | { kind: "holder"; peer: Peer }
  | { kind: "limits" };

const MATRIX_TAGS: [string, string][] = [
  ["func_partnerships", "Partner"], ["func_channel", "Channel"], ["func_bd", "BD"], ["func_sales_leadership", "Sales lead"],
  ["team_mgmt", "People"], ["team_large", "Team 20+"], ["pnl_ownership", "P&L"], ["domain_adtech", "Ad tech"],
  ["domain_mobile", "Mobile"], ["domain_ai", "AI"], ["domain_saas", "SaaS"],
];
const RADAR_ORDER = ["LV", "FN", "DM", "YOE", "UQ", "AC", "CT"];
const SHORT: Record<string, string> = { LV: "Level", FN: "Function", DM: "Domain", YOE: "Years", UQ: "Scarce exp.", AC: "Outcomes", CT: "Company tier" };
const FACTOR_TAGS: Record<string, string[]> = {
  FN: ["func_partnerships", "func_bd", "func_channel"],
  DM: ["domain_ai", "domain_adtech", "domain_mobile", "domain_saas"],
  UQ: ["skill_hyperscaler", "skill_govtech", "skill_consulting_firm_background", "skill_0to1_build", "domain_mobile"],
};
const BANDS = ["Manager / IC", "Director", "Head / Sr Director / GM", "VP", "SVP / MD", "C-level"];
const ord = (n: number) => { const r = Math.round(n); const s = r % 100 >= 11 && r % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][r % 10] ?? "th"; return `${r}${s}`; };

function fmtVal(k: string, v: number | null | undefined) {
  if (v == null) return "—";
  if (k === "LV") return BANDS[Math.round(v)] ?? String(v);
  if (k === "CT") return `Tier ${4 - Math.round(v)}`;
  if (k === "YOE") return `${v} yrs`;
  if (k === "AC") return `${v} lines`;
  return v.toFixed(2);
}

export default function ScorecardPage() {
  const { data, error, loading } = useFetch<Scorecard>("/api/scorecard");
  const { data: rows } = useFetch<Row[]>("/api/postings");
  const [detail, setDetail] = useState<Detail | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setDetail(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const ranked = useMemo(() => (rows ?? []).filter((r) => r.gate_pass && r.opportunity)
    .sort((a, b) => (b.opportunity!.score - a.opportunity!.score)).slice(0, 5), [rows]);

  if (loading && !data) return <div className="muted">Loading…</div>;
  if (!data) return <ErrorBox msg={error} />;
  if (!data.ready || !data.card || !data.reading) {
    return <><h1>Your standing</h1><Empty>{data.reason} <Link to="/profile">Go to Profile</Link></Empty></>;
  }
  const c = data.card, r = data.reading;
  const fac = (k: string) => c.factors.find((f) => f.factor === k)!;
  const gap = c.gaps[0];

  return (
    <div className="sc">
      <header className="tile-head" style={{ alignItems: "flex-end" }}>
        <div>
          <span className="kick" style={{ color: "var(--muted)" }}>{c.cluster} roles · {c.n_reference} role holders</span>
          <h1 style={{ margin: "4px 0 0" }}>Your standing</h1>
        </div>
        <button className="more-link" onClick={() => setDetail({ kind: "limits" })}>How this is measured ›</button>
      </header>

      <section className="sc-row3">
        <button className="tile hit" onClick={() => setDetail({ kind: "score" })} aria-label="Base score details">
          <Gauge score={c.base_score} median={c.holders.median} />
          <div className="small" style={{ textAlign: "center", color: "var(--ink-2)" }}>Holder median <b style={{ color: "var(--holder)" }}>{c.holders.median.toFixed(1)}</b> · tap for breakdown</div>
        </button>
        <button className="tile hit span2" onClick={() => setDetail({ kind: "position" })} aria-label="Position among holders details">
          <div className="tile-head">
            <span className="tile-title">You among {c.n_reference} role holders</span>
            <span className="big" style={{ color: "var(--accent)" }}>{ord(c.position)} <span className="small muted" style={{ fontWeight: 500 }}>range {Math.round(c.position_ci95[0] ?? 0)}–{Math.round(c.position_ci95[1] ?? 0)}</span></span>
          </div>
          <DotPlot scores={c.holders.scores} you={c.base_score} median={c.holders.median} />
        </button>
      </section>

      <section className="sc-row2">
        <div className="tile">
          <div className="tile-title">Seven factors, you vs the median holder</div>
          <div className="small muted">Percentile within holders. Select a factor for its evidence.</div>
          <Radar factors={c.factors} />
          <div className="legend-dots" style={{ marginBottom: 8 }}><span><span className="sq" style={{ background: "var(--accent-strong)" }} />You</span><span><span className="sq" style={{ background: "var(--holder)" }} />Median holder</span></div>
          {RADAR_ORDER.map((k) => {
            const f = fac(k); const d = f.delta ?? 0;
            return (
              <button key={k} className="fac" onClick={() => setDetail({ kind: "factor", f })}>
                <span>{SHORT[k]}</span>
                <span className="track"><span className="fill" style={{ width: `${f.you_pct ?? 0}%`, background: d > 0.5 ? "var(--bad)" : undefined }} /><span className="tick" style={{ left: `${f.holder_median_pct ?? 0}%` }} /></span>
                <span className={`gapv ${d > 0.5 ? "bad" : d < -0.5 ? "good" : ""}`}>{d > 0 ? `+${d.toFixed(1)}` : d.toFixed(1).replace("-", "−")}</span>
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {gap ? (
            <button className="tile hit" style={{ borderColor: "#3a2a2a" }} onClick={() => setDetail({ kind: "factor", f: fac(gap.factor) })}>
              <div className="tile-head" style={{ marginBottom: 12 }}>
                <span><span className="kick bad">Gap · {gap.class}</span><span style={{ fontSize: 18, fontWeight: 700 }}>{gap.label}</span></span>
                <span className="big" style={{ color: "var(--bad)" }}>{ord(gap.you_pct ?? 0)}</span>
              </div>
              {gap.factor === "CT" && Object.entries(c.holders.tier_share).map(([t, s]) => {
                const mine = r.recent_role && `Tier ${r.recent_role.tier}` === t;
                return (
                  <div key={t} className="fac" style={{ cursor: "inherit" }}>
                    <span>{t}{mine ? " · you" : ""}</span>
                    <span className="track"><span className="fill" style={{ width: `${100 * s}%`, background: mine ? "var(--bad)" : undefined }} /></span>
                    <span className="gapv">{Math.round(100 * s)}%</span>
                  </div>
                );
              })}
              <div className="small" style={{ color: "var(--ink-2)", marginTop: 8 }}>{gap.action} {gap.months_to_close != null ? `About ${gap.months_to_close} months.` : ""} {gap.closable_by_target === false ? "Not closable before your target date." : gap.closable_by_target ? "Closable before your target date." : ""}</div>
            </button>
          ) : (
            <div className="tile"><span className="kick good">No factor gap</span>You meet or exceed the median holder on every factor.</div>
          )}
          <button className="tile hit" onClick={() => setDetail({ kind: "focus" })}>
            <span className="kick warn">Focus areas · {c.focus_areas.length}</span>
            <span style={{ fontSize: 17, fontWeight: 700 }}>{c.focus_areas.map((f) => f.label).join(", ") || "None"}</span>
          </button>
          <button className="tile hit" onClick={() => setDetail({ kind: "rare" })}>
            <span className="kick good">Rare strengths · {c.rare_strengths.length}</span>
            {c.rare_strengths.map((x) => (
              <div key={x.tag} className="fac" style={{ cursor: "inherit", padding: "4px 0" }}>
                <span>{x.tag === "team_large" && r.team_size_max ? `Team of ${r.team_size_max.size}` : x.label}</span>
                <span className="track"><span className="fill" style={{ width: `${Math.max(2, 100 * x.holder_share)}%`, background: "var(--holder)" }} /></span>
                <span className="gapv muted">{Math.round(100 * x.holder_share)}% have</span>
              </div>
            ))}
          </button>
        </div>
      </section>

      <section className="tile" style={{ overflowX: "auto" }}>
        <div className="tile-head">
          <span className="tile-title">Qualifications by role</span>
          <span className="legend-dots">
            <span><span className="sq" style={{ background: "var(--accent-strong)" }} />recent</span>
            <span><span className="sq" style={{ background: "var(--dim)" }} />partial or over 8 years ago</span>
            <span><span className="sq" style={{ background: "var(--line)" }} />none</span>
          </span>
        </div>
        <div className="matrix" style={{ gridTemplateColumns: `200px repeat(${MATRIX_TAGS.length}, minmax(44px, 1fr))` }}>
          <div />
          {MATRIX_TAGS.map(([, l]) => <div key={l} className="colh">{l}</div>)}
          {r.roles.map((role) => (
            <MatrixRow key={role.key} role={role} onRole={() => setDetail({ kind: "role", role })} onCell={(tag) => setDetail({ kind: "cell", role, tag })} />
          ))}
          <div className="small muted" style={{ paddingRight: 8 }}>Holders who have it</div>
          {MATRIX_TAGS.map(([t]) => <div key={t} className="prev">{Math.round(100 * (c.prevalence[t] ?? 0))}%</div>)}
        </div>
        <Link className="more-link" to="/roles">Review and confirm roles →</Link>
      </section>

      <section className="sc-row2">
        <div className="tile">
          <div className="tile-title" style={{ marginBottom: 10 }}>Open roles ranked for you</div>
          {ranked.length === 0 ? <div className="muted small">No gate-passing postings yet.</div> : ranked.map((row) => (
            <button key={row.posting.id} className="hit rank-row" onClick={() => setDetail({ kind: "posting", row })}>
              <span><b>{row.posting.company}</b><br /><span className="small muted">{row.posting.title}</span></span>
              <span className="track"><span className="fill" style={{ width: `${row.opportunity!.score}%` }} /></span>
              <b>{row.opportunity!.score.toFixed(1)}</b>
            </button>
          ))}
          <Link className="more-link" to="/postings">All postings →</Link>
        </div>
        <div className="tile">
          <div className="tile-title" style={{ marginBottom: 10 }}>Closest role holders</div>
          {c.peers.slice(0, 5).map((p, i) => (
            <button key={i} className="hit rank-row" onClick={() => setDetail({ kind: "holder", peer: p })}>
              <span><b>{p.company}</b><br /><span className="small muted">{p.title}</span></span>
              <span className="track"><span className="fill" style={{ width: `${p.score}%`, background: "var(--dot)" }} /></span>
              <b>{p.score.toFixed(1)}</b>
            </button>
          ))}
        </div>
      </section>

      {detail && <DetailPanel d={detail} c={c} r={r} notes={data.notes ?? []} reference={data.reference} onClose={() => setDetail(null)} onOpen={setDetail} />}
    </div>
  );
}

function MatrixRow({ role, onRole, onCell }: { role: RoleRead; onRole: () => void; onCell: (t: string) => void }) {
  return (
    <>
      <button className="rowh" onClick={onRole} title={`${role.company} · ${role.title}`}>{role.company} · {role.title}</button>
      {MATRIX_TAGS.map(([t, l]) => {
        const v = (role.final[t] ?? 0) * role.recency_weight;
        const cls = v >= 1 ? "v2" : v > 0 ? "v1" : "v0";
        return <button key={t} className={`cell ${cls}`} onClick={() => onCell(t)} aria-label={`${role.company}, ${l}: ${v >= 1 ? "has, recent" : v > 0 ? "partial or older" : "none"}`} />;
      })}
    </>
  );
}

function Gauge({ score, median }: { score: number; median: number }) {
  const pt = (v: number, rad: number) => { const t = Math.PI * (1 - v / 100); return [130 + rad * Math.cos(t), 130 - rad * Math.sin(t)]; };
  const [ex, ey] = pt(score, 110); const [m1x, m1y] = pt(median, 96); const [m2x, m2y] = pt(median, 124);
  return (
    <svg width="100%" height="150" viewBox="0 0 260 150" role="img" aria-label={`Base score ${score} of 100; holder median ${median}`}>
      <path d="M20,130 A110,110 0 0 1 240,130" fill="none" stroke="var(--line)" strokeWidth="18" strokeLinecap="round" />
      <path d={`M20,130 A110,110 0 0 1 ${ex.toFixed(1)},${ey.toFixed(1)}`} fill="none" stroke="var(--accent-strong)" strokeWidth="18" strokeLinecap="round" />
      <line x1={m1x} y1={m1y} x2={m2x} y2={m2y} stroke="var(--holder)" strokeWidth="3" />
      <text x="130" y="112" textAnchor="middle" fontSize="44" fontWeight="800" className="svg-ink">{score.toFixed(1)}</text>
      <text x="130" y="138" textAnchor="middle" className="svg-text">base score of 100</text>
    </svg>
  );
}

function DotPlot({ scores, you, median }: { scores: number[]; you: number; median: number }) {
  const x = (v: number) => 20 + v * 8.6;
  const placed: [number, number][] = [];
  const dots = scores.map((v) => {
    const cx = x(v); let k = 0;
    while (placed.some(([px, py]) => Math.abs(px - cx) < 11 && py === k)) k++;
    placed.push([cx, k]);
    return { cx, cy: 96 - k * 12, v };
  });
  return (
    <svg width="100%" height="140" viewBox="0 0 900 140" role="img" aria-label={`Dot plot of ${scores.length} holder scores; you ${you}, median ${median}`}>
      <line x1="20" y1="104" x2="880" y2="104" stroke="var(--line)" />
      {dots.map((d, i) => <circle key={i} cx={d.cx} cy={d.cy} r="5" fill="var(--dot)"><title>{`Holder score ${d.v}`}</title></circle>)}
      <line x1={x(median)} y1="30" x2={x(median)} y2="104" stroke="var(--holder)" strokeDasharray="4 4" />
      <text x={x(median) - 6} y="24" textAnchor="end" fontSize="12" fill="var(--holder)">median {median.toFixed(1)}</text>
      <line x1={x(you)} y1="30" x2={x(you)} y2="104" stroke="var(--accent-strong)" strokeWidth="2" />
      <circle cx={x(you)} cy="60" r="9" fill="var(--accent-strong)" stroke="var(--bg)" strokeWidth="2" />
      <text x={x(you) + 8} y="24" fontSize="13" fontWeight="700" className="svg-ink">you {you.toFixed(1)}</text>
      <text x="20" y="128" className="svg-text">0</text>
      <text x="450" y="128" textAnchor="middle" className="svg-text">50</text>
      <text x="880" y="128" textAnchor="end" className="svg-text">100</text>
    </svg>
  );
}

function Radar({ factors }: { factors: Factor[] }) {
  const get = (k: string) => factors.find((f) => f.factor === k)!;
  const pt = (i: number, v: number, R = 130) => { const a = -Math.PI / 2 + (i * 2 * Math.PI) / 7; return [170 + (R * v / 100) * Math.cos(a), 170 + (R * v / 100) * Math.sin(a)]; };
  const poly = (vals: number[]) => vals.map((v, i) => pt(i, v).map((n) => n.toFixed(1)).join(",")).join(" ");
  const you = RADAR_ORDER.map((k) => get(k).you_pct ?? 0), med = RADAR_ORDER.map((k) => get(k).holder_median_pct ?? 0);
  return (
    <svg width="100%" height="300" viewBox="0 0 340 340" role="img" aria-label="Radar chart of seven factor percentiles, you against the median holder">
      <polygon points={poly(Array(7).fill(100))} fill="none" stroke="var(--line)" />
      <polygon points={poly(Array(7).fill(50))} fill="none" stroke="var(--line)" />
      <polygon points={poly(med)} fill="var(--holder)" fillOpacity="0.14" stroke="var(--holder)" strokeWidth="2" />
      <polygon points={poly(you)} fill="var(--accent-strong)" fillOpacity="0.22" stroke="var(--accent-strong)" strokeWidth="2.5" />
      {RADAR_ORDER.map((k, i) => {
        const [lx, ly] = pt(i, 100, 150);
        const anchor = Math.abs(lx - 170) < 10 ? "middle" : lx > 170 ? "start" : "end";
        const d = get(k).delta ?? 0;
        return <text key={k} x={lx} y={ly + 4} textAnchor={anchor} fontSize="12" fill={d > 0.5 ? "var(--bad)" : "var(--ink)"}>{SHORT[k]}</text>;
      })}
    </svg>
  );
}

/* ---------------- detail panel ---------------- */

function DetailPanel({ d, c, r, notes, reference, onClose, onOpen }: {
  d: Detail; c: Card; r: Reading; notes: string[]; reference?: { source: string; as_of: string };
  onClose: () => void; onOpen: (d: Detail) => void;
}) {
  return (
    <div className="panel-wrap" onClick={onClose}>
      <aside className="panel" role="dialog" aria-modal="true" aria-label="Details" onClick={(e) => e.stopPropagation()}>
        <div className="panel-top"><span className="kick" style={{ color: "var(--muted)" }}>Detail</span><button className="x" onClick={onClose} aria-label="Close details">×</button></div>
        <PanelBody d={d} c={c} r={r} notes={notes} reference={reference} onOpen={onOpen} />
      </aside>
    </div>
  );
}

function PanelBody({ d, c, r, notes, reference, onOpen }: {
  d: Detail; c: Card; r: Reading; notes: string[]; reference?: { source: string; as_of: string }; onOpen: (d: Detail) => void;
}) {
  const label = (t: string) => c.tag_labels[t] ?? t;
  switch (d.kind) {
    case "score":
      return (<>
        <h2>Base score {c.base_score.toFixed(1)}</h2>
        <p className="small" style={{ color: "var(--ink-2)" }}>Weighted mean of your percentile on seven factors, within people who hold {c.cluster} roles. Weights blend an expert prior with how strongly each factor separates holders from other hires.</p>
        <h3>Weights and your contribution</h3>
        {c.factors.slice().sort((a, b) => b.weight - a.weight).map((f) => (
          <button key={f.factor} className="fac" onClick={() => onOpen({ kind: "factor", f })}>
            <span>{SHORT[f.factor]}</span>
            <span className="track"><span className="fill" style={{ width: `${f.weight * 2.5}%` }} /></span>
            <span className="gapv">{f.weight.toFixed(1)}%</span>
          </button>
        ))}
        <dl className="kv"><dt>Holder median</dt><dd>{c.holders.median}</dd><dt>Middle half</dt><dd>{c.holders.p25}–{c.holders.p75}</dd><dt>Reference set</dt><dd>{c.n_reference} holders{reference ? ` · ${reference.source}` : ""}</dd></dl>
      </>);
    case "position":
      return (<>
        <h2>{ord(c.position)} percentile</h2>
        <p className="small" style={{ color: "var(--ink-2)" }}>Share of the {c.n_reference} role holders whose base score is below yours. The range is a 95% bootstrap interval: resampling the holders 1,000 times.</p>
        <dl className="kv"><dt>Your score</dt><dd>{c.base_score}</dd><dt>95% range</dt><dd>{ord(c.position_ci95[0] ?? 0)} – {ord(c.position_ci95[1] ?? 0)}</dd><dt>Holders above you</dt><dd>{c.holders.scores.filter((s) => s > c.base_score).length} of {c.n_reference}</dd><dt>Highest holder</dt><dd>{Math.max(...c.holders.scores)}</dd></dl>
        <h3>Score bands</h3>
        {c.holders.hist.counts.map((n, i) => n > 0 && (
          <div key={i} className="fac" style={{ cursor: "inherit" }}><span>{i * 10}–{i * 10 + 10}</span><span className="track"><span className="fill" style={{ width: `${(100 * n) / Math.max(...c.holders.hist.counts)}%`, background: c.base_score >= i * 10 && c.base_score < i * 10 + 10 ? undefined : "var(--dot)" }} /></span><span className="gapv">{n}</span></div>
        ))}
      </>);
    case "factor": {
      const f = d.f; const gap = c.gaps.find((g) => g.factor === f.factor); const dd = f.delta ?? 0;
      const tags = FACTOR_TAGS[f.factor] ?? [];
      const ev = r.evidence.filter((e) => tags.includes(e.tag));
      return (<>
        <span className={`kick ${dd > 0.5 ? "bad" : dd < -0.5 ? "good" : "acc"}`}>{dd > 0.5 ? "Gap" : dd < -0.5 ? "Lead" : "Even"} · weight {f.weight}%</span>
        <h2>{f.label}</h2>
        <dl className="kv">
          <dt>You</dt><dd>{fmtVal(f.factor, f.you_value)} · {ord(f.you_pct ?? 0)} percentile</dd>
          <dt>Median holder</dt><dd>{fmtVal(f.factor, f.holder_median_value)}</dd>
          <dt>Holders above you</dt><dd>{Math.round(100 * (f.share_above_you ?? 0))}%</dd>
          <dt>Weighted gap</dt><dd>{dd > 0 ? "+" : ""}{dd.toFixed(1)} points</dd>
        </dl>
        {gap && <div className="callout">{gap.class === "structural" ? "Structural · stepping stone. " : "Capability · focus area. "}{gap.action} {gap.months_to_close != null ? `About ${gap.months_to_close} months to close.` : ""}</div>}
        {f.factor === "CT" && (<>
          <h3>Scored role</h3>
          <p className="small">{r.recent_role ? `${r.recent_role.title} @ ${r.recent_role.company} (${r.recent_role.months} months, Tier ${r.recent_role.tier}). The most recent role held 12 months or more is scored.` : "—"}</p>
          <h3>Holders' recent employer tier</h3>
          {Object.entries(c.holders.tier_share).map(([t, s]) => <div key={t} className="fac" style={{ cursor: "inherit" }}><span>{t}</span><span className="track"><span className="fill" style={{ width: `${100 * s}%` }} /></span><span className="gapv">{Math.round(100 * s)}%</span></div>)}
        </>)}
        {(f.factor === "LV" || f.factor === "YOE") && (<>
          <h3>Roles read</h3>
          <ul className="ev">{r.roles.map((x) => <li key={x.key}><div className="src">{x.start} – {x.end} · {x.months} months{x.counted ? "" : " · not counted"}</div><b>{x.title}</b> · {x.company}{f.factor === "LV" && x.level != null ? ` · ${BANDS[x.level]}` : ""}</li>)}</ul>
        </>)}
        {f.factor === "AC" && (<>
          <h3>Quantified outcomes found</h3>
          <ul className="ev">{r.achievements.map((a, i) => <li key={i}><div className="src">{a.role}</div>{a.line}</li>)}</ul>
        </>)}
        {ev.length > 0 && (<>
          <h3>Evidence</h3>
          <ul className="ev">{ev.map((e, i) => <li key={i}><div className="src">{label(e.tag)} · {e.source} · weight {e.weight}</div>“{e.phrase}”<div className="small muted">{e.role}</div></li>)}</ul>
        </>)}
      </>);
    }
    case "focus":
      return (<>
        <span className="kick warn">Focus areas</span><h2>Common among holders, weaker in your record</h2>
        <ul className="ev">{c.focus_areas.map((x) => <li key={x.tag}><div className="src">{Math.round(100 * x.holder_share)}% of holders</div><b>{x.label}</b> — yours {x.status}.{x.note ? ` ${x.note}.` : ""}</li>)}</ul>
        <p className="small muted">Confirm any of these that you have done on the Role review page; confirmed values are scored.</p>
        <Link className="more-link" to="/roles">Open Role review →</Link>
      </>);
    case "rare":
      return (<>
        <span className="kick good">Rare strengths</span><h2>In your record, held by under 30% of holders</h2>
        <ul className="ev">{c.rare_strengths.map((x) => {
          const ev = r.evidence.filter((e) => e.tag === x.tag);
          return <li key={x.tag}><div className="src">{Math.round(100 * x.holder_share)}% of holders</div><b>{x.label}</b>{ev.map((e, i) => <div key={i} className="small muted">{e.role} · {e.source}: “{e.phrase}”</div>)}</li>;
        })}</ul>
        <p className="small muted">Shown for positioning; not part of the base score.</p>
      </>);
    case "cell": {
      const { role, tag } = d; const a = role.auto[tag]; const v = role.final[tag] ?? 0;
      return (<>
        <span className="kick acc">{role.company}</span><h2>{label(tag)}</h2>
        <dl className="kv">
          <dt>Role</dt><dd>{role.title} · {role.start} – {role.end}</dd>
          <dt>Value</dt><dd>{v >= 1 ? "Has" : v > 0 ? "Partial" : "No"}{role.recency_weight < 1 && v > 0 ? " · counts half (ended over 8 years ago)" : ""}</dd>
          <dt>Found by</dt><dd>{a ? `${a.source}: “${a.phrase}”` : "not found automatically"}</dd>
          <dt>Your review</dt><dd>{role.reviewed ? "Confirmed" : "Not reviewed"}</dd>
          <dt>Holders who have it</dt><dd>{Math.round(100 * (c.prevalence[tag] ?? 0))}%</dd>
        </dl>
        <button className="more-link" onClick={() => onOpen({ kind: "role", role })}>Whole role →</button>
        <Link className="more-link" to="/roles">Change on Role review →</Link>
      </>);
    }
    case "role": {
      const role = d.role;
      return (<>
        <span className="kick acc">{role.company} · {role.start} – {role.end}</span><h2>{role.title}</h2>
        <dl className="kv">
          <dt>Months</dt><dd>{role.months}{role.counted ? "" : " · evidence only"}</dd>
          <dt>Band</dt><dd>{role.level != null ? BANDS[role.level] : "—"}</dd>
          <dt>Employer tier</dt><dd>Tier {role.tier}</dd>
          <dt>Template</dt><dd>{role.families.join(" + ") || "—"}</dd>
          <dt>Team size</dt><dd>{role.team_size ?? "—"}</dd>
          <dt>Review</dt><dd>{role.reviewed ? "Confirmed by you" : "Not reviewed"}</dd>
        </dl>
        <h3>Qualifications</h3>
        <ul className="ev">{Object.keys(c.tag_labels).map((t) => {
          const v = role.final[t] ?? 0; const a = role.auto[t];
          return <li key={t} style={{ opacity: v ? 1 : 0.55 }}><div className="src">{v >= 1 ? "Has" : v > 0 ? "Partial" : "No"}{a ? ` · ${a.source}` : ""}</div><b>{label(t)}</b>{a ? <div className="small muted">“{a.phrase}”</div> : null}</li>;
        })}</ul>
        <Link className="more-link" to="/roles">Review this role →</Link>
      </>);
    }
    case "posting": {
      const { row } = d; const o = row.opportunity!; const p = row.posting;
      return (<>
        <span className="kick acc">{p.company}</span><h2>{p.title}</h2>
        <dl className="kv">
          <dt>Opportunity score</dt><dd>{o.score.toFixed(1)} · {ord(o.position)} among holders · {o.delta_vs_base >= 0 ? "+" : ""}{o.delta_vs_base.toFixed(1)} vs base</dd>
          <dt>Location</dt><dd>{p.location}</dd><dt>Level</dt><dd>{p.level_band}</dd><dt>Pay</dt><dd>{p.pay_range || "Not stated"}</dd>
          <dt>Requirement match</dt><dd>{row.weighted_score.toFixed(2)} (rank {row.rank_score.toFixed(2)})</dd>
        </dl>
        {o.emphasised.length > 0 && <p className="small">This posting weights more heavily: <b>{o.emphasised.join(", ")}</b>.</p>}
        <h3>Weights for this posting</h3>
        {Object.entries(o.weights).sort((a, b) => b[1] - a[1]).map(([k, w]) => (
          <div key={k} className="fac" style={{ cursor: "inherit" }}><span>{SHORT[k]}</span><span className="track"><span className="fill" style={{ width: `${w * 2.5}%` }} /><span className="tick" style={{ left: `${(c.weights[k] ?? 0) * 2.5}%` }} /></span><span className="gapv">{w.toFixed(1)}%</span></div>
        ))}
        <div className="small muted">Bar = this posting · tick = your base weights.</div>
        {o.thresholds.length > 0 && <div className="callout">{o.thresholds.join(" · ")}</div>}
        {row.hard_gaps.length > 0 && (<><h3>Missing minimums</h3><ul className="ev">{row.hard_gaps.map((g) => <li key={g.tag}>{g.label}</li>)}</ul></>)}
        {row.gaps.length > 0 && (<><h3>Requirements not fully met</h3><ul className="ev">{row.gaps.slice(0, 8).map((g) => <li key={g.tag}><div className="src">{g.cls} · {g.pct}% of postings</div>{g.label}</li>)}</ul></>)}
        <a className="more-link" href={p.url} target="_blank" rel="noreferrer">Open posting ↗</a>
      </>);
    }
    case "holder": {
      const p = d.peer;
      return (<>
        <span className="kick acc">Role holder · score {p.score}</span><h2>{p.company} · {p.title}</h2>
        <p className="small muted">Weighted points by factor: right of centre = this holder ahead of you, left = you ahead.</p>
        {Object.entries(p.components).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
          <div key={k} className="fac" style={{ cursor: "inherit", gridTemplateColumns: "150px minmax(0,1fr) 56px" }}>
            <span>{k.replace(" (recent employer)", "")}</span>
            <span className="track" style={{ background: "var(--line)" }}>
              <span style={{ position: "absolute", left: "50%", top: -3, width: 1, height: 16, background: "var(--muted)" }} />
              <span style={{ position: "absolute", height: 10, borderRadius: 5, background: v > 0 ? "var(--bad)" : "var(--good)", left: v > 0 ? "50%" : `${50 + Math.max(-50, v * 5)}%`, width: `${Math.min(50, Math.abs(v) * 5)}%` }} />
            </span>
            <span className={`gapv ${v > 0.5 ? "bad" : v < -0.5 ? "good" : ""}`}>{v > 0 ? "+" : ""}{v.toFixed(1)}</span>
          </div>
        ))}
        <h3>Their factor values</h3>
        <dl className="kv">{Object.entries(p.values).map(([k, v]) => <Fragment key={k}><dt>{SHORT[k]}</dt><dd>{fmtVal(k, v)}</dd></Fragment>)}</dl>
        <p className="small muted">Shown by current company and title only.</p>
      </>);
    }
    case "limits":
      return (<>
        <h2>How this is measured</h2>
        <ul className="ev">{notes.map((n) => <li key={n}>{n}</li>)}</ul>
        {reference && <p className="small muted">Reference set: {reference.source}.</p>}
        <dl className="kv"><dt>Experience read from</dt><dd>{r.source === "experience" ? "your full experience text" : "your CV"} ({r.format})</dd><dt>Counted years</dt><dd>{r.years}</dd><dt>Highest band held 12+ months</dt><dd>{r.level_max ?? "—"}</dd></dl>
      </>);
  }
}
