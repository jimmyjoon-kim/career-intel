import { Link } from "react-router-dom";
import { useFetch } from "./components";

type Item = { id: number; company: string; title: string; match: number; url: string; quote?: string };
type Reloc = {
  us_postings: number;
  you: { months: Record<string, number>; us_role_months: number; us_evidence: string[]; multi_evidence: string[]; us_education: string[];
    us_market_match: number; multi_region_match: number };
  authorization: { needs_sponsorship: boolean; postings_without_sponsorship: number; line: string };
  effect: { strong_now: number; avg_now: number; strong_if_full: number; avg_if_full: number; strong_if_none: number; avg_if_none: number };
  asks_us: Item[]; asks_multi: Item[]; relocation_offered: Item[]; relocation_not_offered: Item[]; onsite: Item[];
  peers: { holders: number; with_location_data: number; share_with_us_roles?: number; median_us_months?: number };
  target_date: string; method: string[];
};

const yrs = (m: number) => (m >= 12 ? `${Math.round(m / 12)} yrs` : `${m} mos`);
const lvl = (x: number) => (x >= 1 ? "have" : x > 0 ? "partial" : "not shown");

function List({ items, quote = true }: { items: Item[]; quote?: boolean }) {
  return <ul className="small" style={{ margin: "4px 0", paddingLeft: 18 }}>{items.slice(0, 6).map((i) => (
    <li key={i.id}><a href={i.url} target="_blank" rel="noreferrer">{i.company} — {i.title}</a> · match {i.match}%
      {quote && i.quote && <span className="muted"> · “{i.quote}”</span>}</li>))}
    {items.length > 6 && <li className="muted">and {items.length - 6} more</li>}</ul>;
}

// APAC → US: what the move changes in your matching, measured on the US postings you are shown.
export default function RelocationPanel({ family }: { family: string }) {
  const { data: d } = useFetch<Reloc>(`/api/scorecard/relocation?family=${encodeURIComponent(family)}`);
  if (!d || !d.us_postings) return null;
  const m = d.you.months, e = d.effect;
  const gain = e.strong_if_full - e.strong_now;
  return (
    <section className="tile">
      <div className="tile-head">
        <span className="tile-title">Moving to a US role: what it changes</span>
        <span className="small muted">{d.us_postings} US postings you are shown</span>
      </div>
      <div className="grid2">
        <div>
          <span className="kick acc">Your geography</span>
          <p className="small" style={{ margin: "4px 0" }}>
            APAC {yrs(m.APAC || 0)} · US-only roles {yrs(d.you.us_role_months)} · multi-location {yrs(m.multi || 0)}
            {m.EMEA ? ` · EMEA ${yrs(m.EMEA)}` : ""}
          </p>
          <p className="small" style={{ margin: "4px 0" }}><b>Work authorization:</b> {d.authorization.line}</p>
          {d.you.us_education.length > 0 && <p className="small" style={{ margin: "4px 0" }}><b>US education:</b> {d.you.us_education.join("; ")}</p>}
          <p className="small" style={{ margin: "4px 0" }}><b>US market experience:</b> {lvl(d.you.us_market_match)}
            {d.you.us_evidence[0] && <span className="muted"> · {d.you.us_evidence[0]}</span>}</p>
          <p className="small" style={{ margin: "4px 0" }}><b>Multi-region scope:</b> {lvl(d.you.multi_region_match)}
            {d.you.multi_evidence[0] && <span className="muted"> · {d.you.multi_evidence[0]}</span>}</p>
        </div>
        <div>
          <span className="kick acc">Measured effect on your US matches</span>
          <p className="small" style={{ margin: "4px 0" }}>Now: <b>{e.strong_now}</b> strong matches, average match {e.avg_now}%.</p>
          <p className="small" style={{ margin: "4px 0" }}>With US market experience fully shown: {e.strong_if_full} strong ({gain >= 0 ? "+" : ""}{gain}), average {e.avg_if_full}%.</p>
          <p className="small" style={{ margin: "4px 0" }}>With none shown: {e.strong_if_none} strong, average {e.avg_if_none}%.</p>
          <p className="small muted" style={{ margin: "4px 0" }}>
            Peers: {d.peers.with_location_data >= 20 && d.peers.share_with_us_roles != null
              ? `${Math.round(100 * d.peers.share_with_us_roles)}% of holders had US roles (median ${yrs(d.peers.median_us_months ?? 0)}).`
              : `no comparison yet: location is recorded for ${d.peers.with_location_data} of ${d.peers.holders} holders (needs 20).`}
          </p>
        </div>
      </div>
      <div className="grid2">
        <div className="prop">
          <b>Ask for US / North America market experience · {d.asks_us.length}</b>
          {d.asks_us.length ? <List items={d.asks_us} /> : <p className="small muted">None of these postings.</p>}
          <p className="small muted" style={{ marginBottom: 0 }}>To close: show US-facing work you have actually done (US-headquartered partners or clients, US launches, work with US teams) on <Link to="/profile">Profile → Evidence by requirement</Link>. After the move, US-based work adds it.</p>
        </div>
        <div className="prop">
          <b className="good">Ask for international / multi-region scope · {d.asks_multi.length}</b>
          {d.asks_multi.length ? <List items={d.asks_multi} /> : <p className="small muted">None of these postings.</p>}
          <p className="small muted" style={{ marginBottom: 0 }}>Where your APAC regional record counts in your favor.</p>
        </div>
      </div>
      <p className="small" style={{ marginBottom: 2 }}>
        <b>Relocation stated:</b> assistance offered {d.relocation_offered.length} · not offered {d.relocation_not_offered.length} · in-office or on-site stated {d.onsite.length}
        {d.target_date && <> · your target date {d.target_date}</>}
      </p>
      <details><summary className="small muted">How this is measured</summary>
        <ul className="small muted">{d.method.map((x) => <li key={x}>{x}</li>)}</ul></details>
    </section>
  );
}
