import { useState } from "react";
import { Link } from "react-router-dom";
import { useFetch } from "./components";

type Peer = { factor: string; label: string; you_pct: number; median_pct: number; weight: number; points: number; state: "lead" | "gap" | "level"; plain: string };
type Action = { kind: string; title: string; why: string; where: string; effect: string; months: number | null; by_target: boolean | null };
type Edge = { label: string; detail: string; postings: string[] };
type Focus = {
  ready: boolean; reason?: string;
  standing: { score: number; rank: number; of: number; median: number; top: number; lines: string[] };
  versus_peers: Peer[]; actions: Action[]; edge: Edge[]; strong_matches_now: number; postings_considered: number; method: string[];
};

const KIND: Record<string, { label: string; tone: string }> = {
  quick: { label: "Quick win", tone: "good" },
  scheduled: { label: "Already under way", tone: "acc" },
  evidence: { label: "Show evidence", tone: "acc" },
  requirement: { label: "Build", tone: "warn" },
  score: { label: "Raise a factor", tone: "warn" },
  structural: { label: "Long-term", tone: "" },
};

function PeerBars({ rows }: { rows: Peer[] }) {
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.points)));
  return (
    <div role="img" aria-label="Your lead or gap against the median role holder, by factor, in score points">
      {rows.map((r) => (
        <div key={r.factor} style={{ display: "grid", gridTemplateColumns: "minmax(110px, 160px) 1fr 1fr 64px", alignItems: "center", gap: 6, margin: "5px 0" }}>
          <span className="small">{r.label}</span>
          <span style={{ display: "flex", justifyContent: "flex-end" }}>
            {r.points < 0 && <span title={r.plain} style={{ height: 12, width: `${(100 * -r.points) / max}%`, background: "var(--bad)", borderRadius: "6px 0 0 6px" }} />}
          </span>
          <span style={{ borderLeft: "1px solid var(--line)" }}>
            {r.points > 0 && <span title={r.plain} style={{ display: "block", height: 12, width: `${(100 * r.points) / max}%`, background: "var(--good)", borderRadius: "0 6px 6px 0" }} />}
          </span>
          <span className={`small ${r.state === "lead" ? "good" : r.state === "gap" ? "bad" : "muted"}`} style={{ textAlign: "right" }}>
            {r.points > 0 ? "+" : ""}{r.points}
          </span>
        </div>
      ))}
      <div className="small muted" style={{ display: "grid", gridTemplateColumns: "minmax(110px, 160px) 1fr 1fr 64px", gap: 6 }}>
        <span /><span style={{ textAlign: "right" }}>behind the median holder</span><span>ahead</span><span />
      </div>
    </div>
  );
}

export default function FocusPanel() {
  const { data } = useFetch<Focus>("/api/scorecard/focus");
  const [showAll, setShowAll] = useState(false);
  if (!data?.ready) return null;
  const s = data.standing;
  const acts = showAll ? data.actions : data.actions.slice(0, 6);
  const leads = data.versus_peers.filter((p) => p.state === "lead").length;
  const gaps = data.versus_peers.filter((p) => p.state === "gap").length;

  return (
    <>
      <section className="sc-row2">
        <div className="tile">
          <span className="kick acc">What your score means</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12, margin: "6px 0 8px" }}>
            <span style={{ fontSize: 40, fontWeight: 800 }}>{s.score}</span>
            <span className="small">ranks <b>{s.rank} of {s.of}</b> · median holder {s.median} · top holder {s.top}</span>
          </div>
          {s.lines.map((l, i) => <p key={i} className="small" style={{ margin: "4px 0" }}>{l}</p>)}
        </div>
        <div className="tile">
          <span className="kick acc">You vs role holders · {leads} ahead, {gaps} behind</span>
          <p className="small muted" style={{ margin: "4px 0 6px" }}>Score points each factor adds or costs you against the median holder (your percentile vs theirs, times the factor's weight).</p>
          <PeerBars rows={data.versus_peers} />
        </div>
      </section>

      <section className="tile">
        <div className="tile-head">
          <span className="tile-title">Your focus plan</span>
          <span className="small muted">{data.strong_matches_now} strong matches among {data.postings_considered} postings now</span>
        </div>
        <p className="small muted" style={{ marginTop: 0 }}>Ranked: quick wins first, then what is already under way, then what to evidence or build. Each effect is measured by rerunning the score or the posting matches with that one change.</p>
        {acts.length === 0 ? <p className="small muted">No actions: nothing open would move your score or matches.</p> : (
          <div>
            {acts.map((a, i) => (
              <div key={i} className="prop" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 10 }}>
                <div>
                  <span className={`chip-d ${KIND[a.kind]?.tone ?? ""}`}>{KIND[a.kind]?.label ?? a.kind}</span>{" "}
                  <b>{a.title}</b>
                  <div className="small" style={{ marginTop: 4 }}>{a.why}</div>
                  <div className="small muted" style={{ marginTop: 2 }}>How: {a.where}</div>
                </div>
                <div style={{ textAlign: "right", minWidth: 120 }}>
                  <div className="good" style={{ fontWeight: 700 }}>{a.effect}</div>
                  <div className="small muted">{a.months === 0 ? "now" : a.months ? `~${a.months} months` : ""}{a.by_target === false ? " · not before your move" : ""}</div>
                </div>
              </div>
            ))}
            {data.actions.length > 6 && <button className="btn ghost" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${data.actions.length}`}</button>}
          </div>
        )}
      </section>

      {data.edge.length > 0 && (
        <section className="tile">
          <span className="tile-title">Your edge: lead with these</span>
          <p className="small muted" style={{ marginTop: 4 }}>Where you are ahead of most people in these roles. Postings listed are open roles that ask for it.</p>
          <div className="grid2">
            {data.edge.map((e) => (
              <div key={e.label} className="prop">
                <b className="good">{e.label}</b> <span className="small muted">· {e.detail}</span>
                {e.postings.length > 0 && <ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>{e.postings.map((p) => <li key={p}>{p}</li>)}</ul>}
              </div>
            ))}
          </div>
          <p className="small muted" style={{ marginBottom: 0 }}>Details: <Link to="/matches">Job matches</Link> · ask the agent on <Link to="/ask">Ask</Link>, e.g. "which roles reward my strengths most?"</p>
        </section>
      )}
    </>
  );
}
