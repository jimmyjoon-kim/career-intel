import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, type Gap, type Row } from "./api";

export function useFetch<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(() => {
    setLoading(true);
    api<T>(path).then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [path]);
  useEffect(reload, [reload]);
  return { data, error, loading, reload, setData };
}

export function PageHead({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p className="muted">{sub}</p>}
      </div>
      {children && <div className="head-actions">{children}</div>}
    </header>
  );
}

export function Bar({ value, tone = "accent" }: { value: number; tone?: "accent" | "warn" | "muted" }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <span className="bar" aria-label={`${Math.round(v * 100)}%`}>
      <span className={`bar-fill ${tone}`} style={{ width: `${v * 100}%` }} />
    </span>
  );
}

const CLS_SHORT: Record<string, string> = { "COMMON MINIMUM": "Common min", MID: "Mid", DISCRIMINATOR: "Discriminator" };

export function ClsBadge({ cls }: { cls: string }) {
  return <span className={`badge cls-${cls.split(" ")[0].toLowerCase()}`}>{CLS_SHORT[cls] ?? cls}</span>;
}

export function MatchPill({ m }: { m: number }) {
  const label = m >= 1 ? "Has" : m >= 0.5 ? "Partial" : "Missing";
  return <span className={`pill m${m >= 1 ? "1" : m >= 0.5 ? "h" : "0"}`}>{label}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ msg }: { msg: string | null }) {
  return msg ? <div className="error">{msg}</div> : null;
}

export function GapLine({ g }: { g: Gap }) {
  return (
    <li className="gap-line">
      <div className="gap-top">
        <span className="gap-label">{g.label}</span>
        <ClsBadge cls={g.cls} />
        <MatchPill m={g.match} />
      </div>
      <div className="muted small">
        In {g.pct}% of the cluster · {g.closable ? "Closable" : "Not readily closable"}
        {g.close_hint ? ` — ${g.close_hint}` : ""}
      </div>
    </li>
  );
}

export function PostingDetail({ row, onClose }: { row: Row; onClose: () => void }) {
  const p = row.posting;
  return (
    <div className="drawer-wrap" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
        <p className="eyebrow">{p.company}</p>
        <h2>{p.title}</h2>
        <p className="muted">{p.location} · {p.remote_flag === "yes" ? "Remote" : p.remote_flag === "hybrid" ? "Hybrid" : p.remote_flag === "no" ? "On-site" : "Remote unstated"}</p>

        <div className={`gate ${row.gate_pass ? "pass" : "fail"}`}>
          {row.gate_pass ? "Passes your gate" : "Fails your gate"}
          {!row.gate_pass && <ul>{row.gate_reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
        </div>

        <dl className="facts">
          <dt>Rank score</dt><dd>{row.rank_score.toFixed(2)} <Bar value={row.rank_score} /></dd>
          <dt>Weighted match</dt><dd>{row.weighted_score.toFixed(2)}</dd>
          <dt>Cluster</dt><dd>{row.cluster}</dd>
          <dt>Level</dt><dd>{p.level_band}</dd>
          <dt>Pay</dt><dd>{p.pay_range || "Not stated"}</dd>
          <dt>Years required</dt><dd>{p.years_required ?? "Unstated"}</dd>
          <dt>Authorisation</dt><dd>{p.auth_text || "None stated"}</dd>
          <dt>Status</dt><dd>{p.status}{p.last_seen ? ` · last checked ${p.last_seen}` : ""}</dd>
        </dl>

        <h3>Hard gaps <span className="muted small">(common-minimum tags you do not fully meet)</span></h3>
        {row.hard_gaps.length ? <ul className="gaps">{row.hard_gaps.map((g) => <GapLine key={g.tag} g={g} />)}</ul> : <p className="muted">None.</p>}

        <h3>Weighted gaps</h3>
        {row.gaps.length ? <ul className="gaps">{row.gaps.map((g) => <GapLine key={g.tag} g={g} />)}</ul> : <p className="muted">None.</p>}

        <a className="btn" href={p.url} target="_blank" rel="noreferrer">Open posting ↗</a>
        {p.verification && <p className="muted small verif">Verification: {p.verification}</p>}
      </aside>
    </div>
  );
}
