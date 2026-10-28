import { useMemo, useState } from "react";
import type { Row } from "../api";
import { Bar, Empty, ErrorBox, PageHead, PostingDetail, useFetch } from "../components";

export default function Postings() {
  const { data, error, loading } = useFetch<Row[]>("/api/postings");
  const [q, setQ] = useState("");
  const [cluster, setCluster] = useState("");
  const [passOnly, setPassOnly] = useState(true);
  const [open, setOpen] = useState<Row | null>(null);

  const clusters = useMemo(() => [...new Set((data ?? []).map((r) => r.posting.role_cluster))].sort(), [data]);
  const rows = useMemo(() => {
    const needle = q.toLowerCase();
    return (data ?? []).filter((r) =>
      (!passOnly || r.gate_pass) &&
      (!cluster || r.posting.role_cluster === cluster) &&
      (!needle || `${r.posting.company} ${r.posting.title} ${r.posting.location}`.toLowerCase().includes(needle)));
  }, [data, q, cluster, passOnly]);

  return (
    <>
      <PageHead title="Postings" sub={data ? `${rows.length} shown of ${data.length}` : undefined} />
      <ErrorBox msg={error} />
      <div className="filters">
        <input placeholder="Search company, title, location" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={cluster} onChange={(e) => setCluster(e.target.value)}>
          <option value="">All clusters</option>
          {clusters.map((c) => <option key={c}>{c}</option>)}
        </select>
        <label className="check"><input type="checkbox" checked={passOnly} onChange={(e) => setPassOnly(e.target.checked)} /> Passing gate only</label>
      </div>
      {loading && !data ? <div className="muted">Loading…</div> : rows.length === 0 ? <Empty>No postings match these filters.</Empty> : (
        <div className="card flush">
          <table className="table">
            <thead><tr><th>Company / role</th><th>Cluster</th><th>Location</th><th>Pay</th><th>Gate</th><th title="Your base score re-weighted by this posting">Opportunity</th><th title="Requirement match, less 10 points per partly met minimum">Match</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.posting.id} className="clickable" onClick={() => setOpen(r)}>
                  <td><div className="strong">{r.posting.company}</div><div className="muted small">{r.posting.title}</div></td>
                  <td className="small">{r.posting.role_cluster}</td>
                  <td className="small">{r.posting.location}{r.posting.remote_flag === "yes" ? " · Remote" : ""}</td>
                  <td className="small">{r.posting.pay_range || "—"}</td>
                  <td>{r.gate_pass ? <span className="badge ok">Pass</span> : <span className="badge no" title={r.gate_reasons.join("; ")}>Fail</span>}</td>
                  <td className="nowrap small">{r.opportunity ? <><span className="num">{r.opportunity.score.toFixed(1)}</span> <span className="muted">· {Math.round(r.opportunity.position)}th</span>{r.opportunity.thresholds.length > 0 && <> <span className="badge hard" title={r.opportunity.thresholds.join("; ")}>Threshold</span></>}</> : <span className="muted">—</span>}</td>
                  <td className="nowrap"><span className="num">{Math.round(r.rank_score * 100)}%</span> <Bar value={r.rank_score} tone={r.gate_pass ? (r.has_zero_hard_gap ? "warn" : "accent") : "muted"} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && <PostingDetail row={open} onClose={() => setOpen(null)} />}
    </>
  );
}
