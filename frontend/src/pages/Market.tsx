import { useState } from "react";
import { Bar, ClsBadge, ErrorBox, PageHead, useFetch } from "../components";

type TagRow = { tag: string; label: string; count: number; n: number; pct: number; cls: string; weight: number };
type MarketData = { clusters: { name: string; n: number; merged_from: string[]; tags: TagRow[] }[]; all: { n: number; tags: TagRow[] } };

export default function Market() {
  const { data, error } = useFetch<MarketData>("/api/market");
  const [sel, setSel] = useState<string>("ALL");
  if (!data) return <ErrorBox msg={error} />;
  const current = sel === "ALL" ? { name: "All clusters", n: data.all.n, merged_from: [], tags: data.all.tags } : data.clusters.find((c) => c.name === sel)!;

  return (
    <>
      <PageHead title="Market requirements" sub="What open postings ask for, classified by how widely each requirement appears." />
      <div className="tabs">
        <button className={sel === "ALL" ? "on" : ""} onClick={() => setSel("ALL")}>All ({data.all.n})</button>
        {data.clusters.map((c) => (
          <button key={c.name} className={sel === c.name ? "on" : ""} onClick={() => setSel(c.name)}>{c.name} ({c.n})</button>
        ))}
      </div>
      <section className="card">
        <div className="legend small muted">
          <span><ClsBadge cls="COMMON MINIMUM" /> ≥70% · weight 0, threshold</span>
          <span><ClsBadge cls="MID" /> 30–70% · weight 1</span>
          <span><ClsBadge cls="DISCRIMINATOR" /> &lt;30% · weight 3</span>
        </div>
        {current.merged_from.length > 0 && <p className="muted small">Includes small clusters merged by tag overlap: {current.merged_from.join(", ")}.</p>}
        <table className="table">
          <thead><tr><th>Requirement</th><th>Share of postings</th><th>Class</th></tr></thead>
          <tbody>
            {current.tags.map((t) => (
              <tr key={t.tag}>
                <td>{t.label}<div className="muted small mono">{t.tag}</div></td>
                <td className="nowrap"><span className="num">{t.pct}%</span> <Bar value={t.pct / 100} /> <span className="muted small">{t.count}/{t.n}</span></td>
                <td><ClsBadge cls={t.cls} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
