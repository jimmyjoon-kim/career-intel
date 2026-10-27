import { Link } from "react-router-dom";
import type { Card, Factor, Scorecard } from "../api";
import { Empty, ErrorBox, PageHead, useFetch } from "../components";

const TIER = (t: number) => `Tier ${t}`;

export default function ScorecardPage() {
  const { data, error, loading } = useFetch<Scorecard>("/api/scorecard");
  if (loading && !data) return <div className="muted">Loading…</div>;
  if (!data) return <ErrorBox msg={error} />;
  if (!data.ready || !data.card || !data.reading) {
    return (
      <>
        <PageHead title="Scorecard" />
        <Empty>{data.reason} <Link to="/profile">Go to Profile</Link></Empty>
      </>
    );
  }
  const c = data.card;
  const r = data.reading;
  const [lo, hi] = c.position_ci95;

  return (
    <>
      <PageHead
        title="Scorecard"
        sub={`You compared with ${c.n_reference} people who hold ${c.cluster} roles. The same reader is applied to your text and theirs.`}
      />

      <section className="kpis">
        <Kpi n={c.base_score.toFixed(1)} label="Base score" sub={`Holder median ${c.holders.median.toFixed(1)} · middle half ${c.holders.p25.toFixed(0)}–${c.holders.p75.toFixed(0)}`} />
        <Kpi n={`${Math.round(c.position)}th`} label="Percentile among holders" sub={lo != null && hi != null ? `95% range ${Math.round(lo)}th–${Math.round(hi)}th` : ""} />
        <Kpi n={String(c.gaps.length)} label={c.gaps.length === 1 ? "Gap" : "Gaps"} sub={c.gaps.map((g) => g.label).join(", ") || "none"} />
        <Kpi n={String(c.differentiators.length)} label="Differentiators" sub={c.differentiators.map((d) => d.label).join(", ") || "none"} />
      </section>

      <div className="grid2">
        <section className="card">
          <h2>Where your score sits</h2>
          <p className="muted small">Base scores of role holders. Your score is the solid line.</p>
          <Histogram card={c} />
        </section>
        <section className="card">
          <h2>Factor by factor</h2>
          <div className="legend-row"><span><i style={{ background: "var(--warn)" }} />Median holder</span><span><i style={{ background: "var(--accent)" }} />You</span></div>
          <Dumbbell factors={c.factors} />
          <p className="muted small">Percentile within holders. Right column: weighted gap (+ holders ahead, − you ahead).</p>
        </section>
      </div>

      <h2>Plan</h2>
      <div className="plan3">
        <section className="card">
          <div className="kicker bad">Gaps</div>
          {c.gaps.length === 0 ? <p className="muted">No factor gap against the median holder.</p> : (
            <ul>{c.gaps.map((g) => (
              <li key={g.factor}>
                <b>{g.label}</b> <span className="badge">{g.class === "structural" ? "Structural · stepping stone" : "Capability · focus area"}</span>
                <div className="small">{Math.round(100 * (g.share_above_you ?? 0))}% of holders are above you. {g.action}</div>
                <div className="small muted">
                  {g.months_to_close != null ? `About ${g.months_to_close} months to close.` : ""}
                  {g.closable_by_target === true ? " Closable before your target date." : g.closable_by_target === false ? " Not closable before your target date." : ""}
                </div>
              </li>
            ))}</ul>
          )}
        </section>
        <section className="card">
          <div className="kicker warn">Focus areas</div>
          <p className="muted small">Tags common among holders that are missing or older than 8 years in your text.</p>
          <ul>{c.focus_areas.map((f) => (
            <li key={f.tag}><b>{f.label}</b>: {Math.round(100 * f.holder_share)}% of holders; yours {f.status}.{f.note ? ` (${f.note})` : ""}</li>
          ))}</ul>
        </section>
        <section className="card">
          <div className="kicker">Lead with</div>
          {c.differentiators.length === 0 ? <p className="muted">None above the median holder.</p> : (
            <ul>{c.differentiators.map((d) => (
              <li key={d.factor}><b>{d.label}</b>: {fmtVal(d.factor, d.you_value)} vs median {fmtVal(d.factor, d.holder_median_value)}; {Math.round(100 * (d.share_above_you ?? 0))}% of holders above you.</li>
            ))}</ul>
          )}
          {c.rare_strengths.length > 0 && (
            <>
              <p className="small" style={{ marginTop: "0.75rem" }}><b>Rare among holders</b> (in your text, held by under 30% of holders; not scored):</p>
              <ul>{c.rare_strengths.map((x) => <li key={x.tag} className="small">{x.label}: {Math.round(100 * x.holder_share)}% of holders</li>)}</ul>
            </>
          )}
        </section>
      </div>

      <section className="card" style={{ marginTop: "1.25rem" }}>
        <h2>Nearest role holders</h2>
        <p className="muted small">Holders whose factor profile is closest to yours. Shown by current company and title only.</p>
        <table className="table">
          <thead><tr><th>Holder (company · title)</th><th>Score</th><th>Ahead of you on</th><th>You lead on</th></tr></thead>
          <tbody>{c.peers.map((p, i) => (
            <tr key={i}><td>{p.company} · {p.title}</td><td className="num">{p.score.toFixed(1)}</td>
              <td className="small">{p.ahead_on.join(", ") || "—"}</td><td className="small">{p.you_lead_on.join(", ") || "—"}</td></tr>
          ))}</tbody>
        </table>
      </section>

      <section className="card">
        <h2>How your profile was read</h2>
        <p className="muted small">
          Source: {r.source === "experience" ? "your full experience text" : "your CV text"} ({r.format} format) · {r.years} counted years ·
          highest band held 12+ months: {r.level_max ?? "—"}.
          {r.team_size_max && <> Largest team: {r.team_size_max.size} ({r.team_size_max.role}; {r.team_size_max.source}).</>}
          {r.recent_role && <> Scored recent role: <b>{r.recent_role.title} @ {r.recent_role.company}</b> ({r.recent_role.months} months, {TIER(r.recent_role.tier)}).</>}
        </p>
        <table className="table">
          <thead><tr><th>Role</th><th>Dates</th><th>Months</th><th>Band</th><th>Employer tier</th><th>Counted</th></tr></thead>
          <tbody>{r.roles.map((x, i) => (
            <tr key={i}><td><div className="strong">{x.title}</div><div className="muted small">{x.company}</div></td>
              <td className="small nowrap">{x.start} – {x.end}</td><td className="num">{x.months}</td>
              <td className="small">{x.level != null ? r.level_names[String(x.level)] : "—"}</td><td className="small">{TIER(x.tier)}</td>
              <td className="small">{x.counted ? "Yes" : "Evidence only"}</td></tr>
          ))}</tbody>
        </table>
        <details>
          <summary className="small">Evidence found ({r.evidence.length} tags, {r.achievements.length} quantified outcomes)</summary>
          <table className="table">
            <thead><tr><th>Tag</th><th>Evidence</th><th>Source</th><th>Role</th><th>Weight</th></tr></thead>
            <tbody>{r.evidence.map((e, i) => (
              <tr key={i}><td className="small">{e.tag}</td>
                <td className="small">{e.url ? <a href={e.url} target="_blank" rel="noreferrer">{e.phrase}</a> : `“${e.phrase}”`}</td>
                <td className="small">{e.source}</td><td className="small">{e.role}</td><td className="num">{e.weight}</td></tr>
            ))}</tbody>
          </table>
          <h3>Quantified outcomes</h3>
          <ul className="small">{r.achievements.map((a, i) => <li key={i}>{a.line} <span className="muted">({a.role})</span></li>)}</ul>
        </details>
      </section>

      <section className="card">
        <h2>Limits of this score</h2>
        <ul className="notes">{(data.notes ?? []).map((n) => <li key={n}>{n}</li>)}</ul>
        {data.reference && <p className="muted small">Reference set: {data.reference.source}.</p>}
      </section>
    </>
  );
}

const BANDS = ["Manager / IC", "Director", "Head / Sr Director / GM", "VP", "SVP / MD", "C-level"];

function fmtVal(k: string, v: number | null) {
  if (v == null) return "—";
  if (k === "LV") return BANDS[Math.round(v)] ?? String(v);
  if (k === "CT") return `Tier ${4 - Math.round(v)}`;
  if (k === "YOE") return `${v} yrs`;
  if (k === "FN" || k === "DM") return v.toFixed(2);
  return String(Math.round(v * 100) / 100);
}

function Kpi({ n, label, sub }: { n: string; label: string; sub: string }) {
  return (
    <div className="kpi">
      <div className="kpi-n">{n}</div>
      <div className="kpi-l">{label}</div>
      <div className="muted small">{sub}</div>
    </div>
  );
}

function Histogram({ card }: { card: Card }) {
  const { counts } = card.holders.hist;
  const W = 440, H = 230, L = 30, R = 12, T = 26, B = 34;
  const max = Math.max(4, ...counts);
  const x = (v: number) => L + (v / 100) * (W - L - R);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const ticks = [0, Math.round(max / 2), max];
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Holder base-score histogram">
        {ticks.map((t) => <g key={t}><line className="grid" x1={L} x2={W - R} y1={y(t)} y2={y(t)} /><text x={L - 6} y={y(t) + 4} textAnchor="end">{t}</text></g>)}
        {counts.map((c, i) => c > 0 && (
          <rect key={i} className="bar-h" x={x(i * 10) + 1} y={y(c)} width={x(10) - x(0) - 2} height={y(0) - y(c)} rx={3}>
            <title>{`Score ${i * 10}–${i * 10 + 10}: ${c} holders`}</title>
          </rect>
        ))}
        {[0, 20, 40, 60, 80, 100].map((t) => <text key={t} x={x(t)} y={H - B + 15} textAnchor="middle">{t}</text>)}
        <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle">Base score (0–100)</text>
        <line className="med" x1={x(card.holders.median)} x2={x(card.holders.median)} y1={T - 6} y2={y(0)} />
        <text x={x(card.holders.median) - 5} y={T - 10} textAnchor="end">median {card.holders.median.toFixed(1)}</text>
        <line className="you" x1={x(card.base_score)} x2={x(card.base_score)} y1={T - 6} y2={y(0)} />
        <text className="strong" x={x(card.base_score) + 5} y={T - 10}>you {card.base_score.toFixed(1)}</text>
      </svg>
    </div>
  );
}

function Dumbbell({ factors }: { factors: Factor[] }) {
  const rows = [...factors].sort((a, b) => (b.delta ?? 0) - (a.delta ?? 0));
  const W = 440, L = 150, R = 72, T = 10, rowH = 28, H = T + rows.length * rowH + 24;
  const x = (v: number) => L + (v / 100) * (W - L - R);
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Your factor percentiles against the median holder">
        {[0, 50, 100].map((t) => <g key={t}><line className="grid" x1={x(t)} x2={x(t)} y1={T} y2={H - 20} /><text x={x(t)} y={H - 6} textAnchor="middle">{t}th</text></g>)}
        {rows.map((f, i) => {
          const cy = T + i * rowH + rowH / 2;
          const d = f.delta ?? 0;
          return (
            <g key={f.factor}>
              <text className="lbl" x={L - 8} y={cy + 4} textAnchor="end">{f.label.replace(" (recent employer)", "")}</text>
              {f.you_pct != null && f.holder_median_pct != null && <line className="conn" x1={x(f.holder_median_pct)} x2={x(f.you_pct)} y1={cy} y2={cy} />}
              {f.holder_median_pct != null && <circle className="dot-med" cx={x(f.holder_median_pct)} cy={cy} r={5.5}><title>{`Median holder: ${f.holder_median_pct}th`}</title></circle>}
              {f.you_pct != null && <circle className="dot-you" cx={x(f.you_pct)} cy={cy} r={5.5}><title>{`You: ${f.you_pct}th`}</title></circle>}
              <text className={d > 0.5 ? "gap" : d < -0.5 ? "lead" : ""} x={W - R + 10} y={cy + 4}>
                {f.delta == null ? "n/a" : d > 0 ? `+${d.toFixed(1)} gap` : `${d.toFixed(1).replace("-", "−")} lead`}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
