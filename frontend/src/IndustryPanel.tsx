import { useState } from "react";
import { useFetch } from "./components";

type Row = { sector: string; label: string; holders: number; with_path: number; switched_in: number; from_your_industry: number;
  your_industry_in_career: number | null; postings: number; your_avg_match: number | null; strong_matches: number; relation: string };
type PeerF = { factor: string; label: string; points: number; state: string; plain: string };
type Ind = {
  you: { home: string | null; home_label: string; months: Record<string, number> };
  sectors: Row[]; target: string; target_label: string; target_summary: Row | null;
  peer: { n: number; min: number; score?: number; rank?: number; of?: number; median?: number; factors?: PeerF[] };
  switchers: { with_path: number; switched_in: number; min: number; from?: [string, number][]; median_years_before?: number;
    median_level?: number; share_ai_degree?: number; share_from_your_industry?: number };
  evidence_now: { n: number; of: number; tag: string } | null;
  gaps: { tag: string; label: string; share_target: number; share_home: number; specific: boolean; match: number; closable: boolean; how: string }[];
  method: string[];
};
const yrs = (m: number) => `${Math.round(m / 12)} yrs`;
const pc = (x: number) => `${Math.round(100 * x)}%`;

// Switching industries: you against the people who hold these roles in the target industry.
export default function IndustryPanel({ family }: { family: string }) {
  const [target, setTarget] = useState<string>("");
  const { data: d } = useFetch<Ind>(`/api/scorecard/industry?family=${encodeURIComponent(family)}${target ? `&target=${target}` : ""}`);
  if (!d) return null;
  const t = d.target_summary, p = d.peer, s = d.switchers;
  return (
    <section className="tile">
      <div className="tile-head">
        <span className="tile-title">Switching industries: you vs the people who hold these roles there</span>
        <span className="small muted">Your industry: {d.you.home_label}</span>
      </div>
      <p className="small muted" style={{ marginTop: 0 }}>Your years by industry: {Object.entries(d.you.months).map(([k, v]) => `${k} ${yrs(v)}`).join(" · ")}</p>
      <div style={{ overflowX: "auto" }}>
        <table className="small" style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr className="muted" style={{ textAlign: "left" }}>
            <th>Industry</th><th>Role holders</th><th>Switched in (of read paths)</th><th>Show your industry in career</th><th>Postings</th><th>Your avg match</th><th /></tr></thead>
          <tbody>{d.sectors.filter((r) => r.holders || r.postings).map((r) => (
            <tr key={r.sector} style={{ borderTop: "1px solid var(--line)", background: r.sector === d.target ? "var(--soft, transparent)" : undefined }}>
              <td><b>{r.label}</b> <span className="muted">· {r.relation}</span></td>
              <td>{r.holders}</td>
              <td>{r.with_path ? `${r.switched_in} of ${r.with_path}` : "—"}</td>
              <td>{r.your_industry_in_career != null && r.holders ? `${r.your_industry_in_career} of ${r.holders}` : "—"}</td>
              <td>{r.postings}</td>
              <td>{r.your_avg_match != null ? `${r.your_avg_match}%` : "—"}</td>
              <td>{r.sector !== d.target && <button className="btn ghost" onClick={() => setTarget(r.sector)}>Compare</button>}</td>
            </tr>))}</tbody>
        </table>
      </div>

      <h3 style={{ margin: "12px 0 4px" }}>Moving into {d.target_label}</h3>
      <div className="grid2">
        <div className="prop">
          <b>You vs {family} holders in this industry</b>
          {p.score != null ? <>
            <p className="small" style={{ margin: "4px 0" }}>Score <b>{p.score}</b> · rank {p.rank} of {p.of} · median holder {p.median}</p>
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{(p.factors ?? []).filter((f) => f.state !== "level").slice(0, 6).map((f) =>
              <li key={f.factor} className={f.state === "lead" ? "good" : "bad"}>{f.label}: {f.plain}</li>)}</ul>
          </> : <p className="small muted">{p.n} holders in this industry; a peer score needs {p.min}.</p>}
          {d.evidence_now && <p className="small" style={{ marginBottom: 0 }}>{d.evidence_now.n} of {d.evidence_now.of} of these holders show {d.evidence_now.tag} in their career (including the current role).</p>}
        </div>
        <div className="prop">
          <b>People who switched into this industry</b>
          {s.from ? <>
            <p className="small" style={{ margin: "4px 0" }}>{s.switched_in} of {s.with_path} holders switched in · came from: {s.from.map(([k, n]) => `${k} ${n}`).join(", ")}</p>
            <p className="small" style={{ margin: "4px 0" }}>Median years before the switch {s.median_years_before} · median level {s.median_level} · AI degree {pc(s.share_ai_degree ?? 0)} · from your industry {pc(s.share_from_your_industry ?? 0)}</p>
          </> : <p className="small muted">Career paths read for {s.with_path} holders here ({s.switched_in} switched in); a summary needs {s.min} switchers. Paths are recorded from new peer research onward.</p>}
          {t && <p className="small" style={{ marginBottom: 0 }}>Postings here: {t.postings} · your average match {t.your_avg_match ?? "—"}% · strong matches {t.strong_matches}</p>}
        </div>
      </div>
      <div className="prop">
        <b>What this industry asks for that you do not fully show</b>
        {d.gaps.length === 0 ? <p className="small muted">Nothing asked by 30%+ of its postings is missing.</p> :
          <ul className="small" style={{ margin: "4px 0", paddingLeft: 18 }}>{d.gaps.map((g) => (
            <li key={g.tag}><b>{g.label}</b> · asked by {pc(g.share_target)} here vs {pc(g.share_home)} in your industry{g.specific && <span className="chip-d warn"> industry-specific</span>}
              {" "}· you: {g.match > 0 ? "partial" : "not shown"} · {g.closable ? `closable: ${g.how || "build or evidence it"}` : "not closable by current work; state it only if you have done it"}</li>))}</ul>}
      </div>
      <details><summary className="small muted">How this is measured</summary><ul className="small muted">{d.method.map((x) => <li key={x}>{x}</li>)}</ul></details>
    </section>
  );
}
