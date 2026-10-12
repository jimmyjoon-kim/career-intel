import { useState } from "react";
import { Link } from "react-router-dom";
import type { Gap, Row } from "../api";
import { Bar, ClsBadge, Empty, ErrorBox, MatchPill, PageHead, PostingDetail, useFetch } from "../components";

type Dash = {
  counts: { postings: number; open: number; gate_pass: number; no_zero_hard_gap: number };
  profile_ready: boolean;
  top: Row[];
  gaps: (Gap & { postings: number; impact: number; hard: boolean })[];
  gate_fail_reasons: { reason: string; count: number }[];
};

export default function Dashboard() {
  const { data, error, loading } = useFetch<Dash>("/api/dashboard");
  const [open, setOpen] = useState<Row | null>(null);
  if (loading && !data) return <div className="muted">Loading…</div>;
  if (!data) return <ErrorBox msg={error} />;
  const maxImpact = Math.max(1, ...data.gaps.map((g) => g.impact));

  return (
    <>
      <PageHead title="Dashboard" sub="Where you stand against open postings that pass your gate." />
      {!data.profile_ready && (
        <div className="notice">
          Your profile has no evidence yet, so every requirement counts as missing. <Link to="/profile">Upload your CV</Link> to score properly.
        </div>
      )}

      <section className="kpis">
        <Kpi n={data.counts.open} label="Open postings" sub={`${data.counts.postings} tracked in total`} />
        <Kpi n={data.counts.gate_pass} label="Pass your gate" sub="level, location, authorisation, status" />
        <Kpi n={data.counts.no_zero_hard_gap} label="No missing minimum" sub="meet or partly meet every common minimum" />
        <Kpi n={data.gaps.filter((g) => g.closable).length} label="Closable gaps" sub={`of top ${data.gaps.length} gaps`} />
      </section>

      <div className="grid2">
        <section className="card">
          <h2>Top matches</h2>
          {data.top.length === 0 ? (
            <Empty>No postings pass your gate yet. Check your preferences on the Profile page.</Empty>
          ) : (
            <table className="table">
              <thead><tr><th>Role</th><th>Rank</th><th>Hard gaps</th></tr></thead>
              <tbody>
                {data.top.map((r) => (
                  <tr key={r.posting.id} className="clickable" onClick={() => setOpen(r)}>
                    <td>
                      <div className="strong">{r.posting.company}</div>
                      <div className="muted small">{r.posting.title}</div>
                    </td>
                    <td className="nowrap">
                      <span className="num">{r.rank_score.toFixed(2)}</span> <Bar value={r.rank_score} tone={r.has_zero_hard_gap ? "warn" : "accent"} />
                    </td>
                    <td>
                      {r.hard_gaps.length === 0 ? <span className="muted small">None</span> :
                        r.hard_gaps.map((g) => <span key={g.tag} className="chip">{g.label} · <MatchPill m={g.match} /></span>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Link className="more" to="/postings">All postings →</Link>
        </section>

        <section className="card">
          <h2>Biggest gaps</h2>
          <p className="muted small">Impact = how often the requirement appears × its weight × your shortfall.</p>
          {data.gaps.length === 0 ? <Empty>No gaps found across passing postings.</Empty> : (
            <ul className="gap-list">
              {data.gaps.map((g) => (
                <li key={g.tag}>
                  <div className="gap-top">
                    <span className="gap-label">{g.label}</span>
                    <ClsBadge cls={g.cls} />
                    <MatchPill m={g.match} />
                    {g.hard && <span className="badge hard">Hard</span>}
                  </div>
                  <div className="gap-meta">
                    <Bar value={g.impact / maxImpact} tone="warn" />
                    <span className="muted small">{g.postings} postings · {g.closable ? "closable" : "not readily closable"}</span>
                  </div>
                  {g.close_hint && <div className="muted small hint">{g.close_hint}</div>}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {data.gate_fail_reasons.length > 0 && (
        <section className="card">
          <h2>Why postings fail your gate</h2>
          <ul className="reasons">
            {data.gate_fail_reasons.map((r) => <li key={r.reason}><span className="num">{r.count}</span> {r.reason}</li>)}
          </ul>
        </section>
      )}
      {open && <PostingDetail row={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function Kpi({ n, label, sub }: { n: number; label: string; sub: string }) {
  return (
    <div className="kpi">
      <div className="kpi-n">{n}</div>
      <div className="kpi-l">{label}</div>
      <div className="muted small">{sub}</div>
    </div>
  );
}
