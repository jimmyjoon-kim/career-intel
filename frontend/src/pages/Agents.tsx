import { Fragment, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Bar, Empty, ErrorBox, PageHead, useFetch } from "../components";
import TagReview from "../TagReview";

type Step = { agent: string; status: string; seconds?: number; cost_usd?: number; result?: unknown; error?: string };
type Run = { id: number; kind: string; status: string; trigger: string; created_at: string; started_at: string | null;
  finished_at: string | null; steps: Step[]; error: string; cost_usd: number };
type Member = { key: string; name: string; model: string; job: string };
type Status = {
  team: Member[]; models: Record<string, string>; critical_model_last_used: string | null;
  budget: { allowance_usd: number; share: number; cap_usd: number; spent_usd: number; calls: number;
    by_agent: Record<string, number>; by_model: Record<string, number> };
  schedule: string[]; runs: Run[]; pending: number; pipelines: string[];
  boards: { ats: string; slug: string; company: string; active: boolean; last_status: string; last_checked: string | null }[];
};
type BriefT = { id: number; created_at: string; body: string; model: string; check: { passed: boolean; issues: string[]; model: string | null } };
type Prop = { id: number; kind: string; title: string; detail: string; status: string; created_at: string; count: number;
  preview: Record<string, unknown>[] };
type Hist = { points: { at: string; score: number; position: number; model_version: string }[] };

const when = (s: string | null) => (s ? new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const usd = (x: number) => `$${x < 1 ? x.toFixed(3) : x.toFixed(2)}`;

function Md({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => { if (list.length) { out.push(<ul key={out.length}>{list.map((l, i) => <li key={i}>{inline(l)}</li>)}</ul>); list = []; } };
  const inline = (s: string) => s.split(/(\*\*[^*]+\*\*)/).map((p, i) => p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p);
  for (const raw of text.split("\n")) {
    const l = raw.trim();
    if (!l) { flush(); continue; }
    if (/^[-*•]\s+/.test(l)) { list.push(l.replace(/^[-*•]\s+/, "")); continue; }
    flush();
    const h = l.replace(/^#+\s*/, "").replace(/^\*\*(.+)\*\*:?$/, "$1");
    out.push(/^#|^\*\*.+\*\*:?$/.test(l) ? <h3 key={out.length}>{h}</h3> : <p key={out.length}>{inline(l)}</p>);
  }
  flush();
  return <div className="brief">{out}</div>;
}

function Spark({ pts }: { pts: Hist["points"] }) {
  if (pts.length < 2) return <div className="muted small">{pts.length === 1 ? `One stored score so far: ${pts[0].score} (${pts[0].model_version}).` : "No stored scores yet."}</div>;
  const w = 320, h = 70, lo = Math.min(...pts.map((p) => p.score)) - 2, hi = Math.max(...pts.map((p) => p.score)) + 2;
  const xy = pts.map((p, i) => [8 + (i * (w - 16)) / (pts.length - 1), h - 8 - ((p.score - lo) / (hi - lo)) * (h - 16)]);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="Score history">
      <polyline fill="none" stroke="var(--acc, #6ea8ff)" strokeWidth="2" points={xy.map((p) => p.join(",")).join(" ")} />
      {xy.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3" fill="var(--acc, #6ea8ff)"><title>{`${when(pts[i].at)} · ${pts[i].score} · ${pts[i].model_version}`}</title></circle>)}
    </svg>
  );
}

export default function Agents() {
  const { user } = useAuth();
  const st = useFetch<Status>("/api/agents/status");
  const br = useFetch<{ brief: BriefT | null }>("/api/agents/brief");
  const hist = useFetch<Hist>("/api/agents/history");
  const [props, setProps] = useState<Prop[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [board, setBoard] = useState({ ats: "greenhouse", slug: "", company: "" });
  const admin = !!user?.is_admin;

  const loadProps = () => api<{ proposals: Prop[] }>("/api/agents/proposals").then((r) => setProps(r.proposals)).catch((e) => setErr(e.message));
  useEffect(() => { if (admin) loadProps(); }, [admin]);  // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn: () => Promise<string>) => {
    setErr(null); setMsg(null);
    try { setMsg(await fn()); st.reload(); } catch (e) { setErr((e as Error).message); }
  };
  const runNow = (kind: string) => act(async () => (await api<{ note: string }>("/api/agents/run", { method: "POST", json: { kind } })).note);
  const decide = (id: number, decision: string) => act(async () => {
    const r = await api<{ note: string }>(`/api/agents/proposals/${id}`, { method: "POST", json: { decision } });
    loadProps(); return r.note;
  });
  const addBoard = (e: FormEvent) => { e.preventDefault(); act(async () => { await api("/api/agents/boards", { method: "POST", json: board }); setBoard({ ...board, slug: "", company: "" }); return "Board added; read on the next daily run."; }); };

  if (st.loading && !st.data) return <div className="muted">Loading…</div>;
  if (!st.data) return <ErrorBox msg={st.error} />;
  const s = st.data, b = s.budget, brief = br.data?.brief;
  const share = b.cap_usd ? Math.min(1, b.spent_usd / b.cap_usd) : 0;
  const costOf = (k: string) => b.by_agent[k] ?? 0;

  return (
    <>
      <PageHead title="Agent team" sub="Runs sourcing, reading, scoring, checking and the weekly brief on a schedule. Changes to the model or the holder pool wait for your approval." />
      {msg && <div className="ok-box">{msg}</div>}
      <ErrorBox msg={err} />

      <section className="kpis">
        <div className="kpi">
          <div className="kpi-n">{usd(b.spent_usd)}</div>
          <div className="kpi-l">API spend this month · cap {usd(b.cap_usd)}</div>
          <Bar value={share} tone={share > 0.8 ? "warn" : "accent"} />
          <div className="muted small">Cap = {Math.round(b.share * 100)}% of {usd(b.allowance_usd)} · {b.calls} calls</div>
        </div>
        <div className="kpi"><div className="kpi-n">{s.pending}</div><div className="kpi-l">Waiting for your decision</div></div>
        <div className="kpi"><div className="kpi-n small" style={{ fontSize: 15 }}>{s.models.critical}</div>
          <div className="kpi-l">Checker and analyst model</div>
          <div className="muted small">{s.critical_model_last_used ? `last used: ${s.critical_model_last_used}` : `fallback: ${s.models.critical_fallback}`}</div></div>
        <div className="kpi"><div className="kpi-n">{s.runs[0]?.status ?? "—"}</div><div className="kpi-l">Last run {s.runs[0] ? `(${s.runs[0].kind}, ${when(s.runs[0].finished_at || s.runs[0].created_at)})` : ""}</div></div>
      </section>

      <div className="grid2">
        <section className="card">
          <h2>Weekly brief</h2>
          {!brief ? <Empty>No brief yet. The first one is written on Monday 09:00 KST{admin ? ", or run the weekly pipeline below" : ""}.</Empty> : (
            <>
              <div className="small muted">{when(brief.created_at)} · written by {brief.model} ·{" "}
                <span className={brief.check.passed ? "good" : "bad"}>{brief.check.passed ? "checker passed" : `checker found ${brief.check.issues.length} issue(s)`}</span>
                {brief.check.model ? ` (${brief.check.model})` : ""}</div>
              <Md text={brief.body} />
              {!brief.check.passed && <ul className="small bad">{brief.check.issues.map((i, k) => <li key={k}>{i}</li>)}</ul>}
            </>
          )}
          <h3>Score history</h3>
          <Spark pts={hist.data?.points ?? []} />
        </section>

        <section className="card">
          <h2>Team</h2>
          <table className="tbl small">
            <thead><tr><th>Agent</th><th>Model</th><th>What it does</th><th>Spend</th></tr></thead>
            <tbody>{s.team.map((m) => (
              <tr key={m.key}><td><strong>{m.name}</strong></td><td className="mono">{s.models[m.model] ?? m.model}</td><td>{m.job}</td><td>{costOf(m.key) ? usd(costOf(m.key)) : "—"}</td></tr>
            ))}</tbody>
          </table>
          <h3>Schedule</h3>
          <ul className="small">{s.schedule.map((x) => <li key={x}>{x}</li>)}</ul>
          {admin && <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{s.pipelines.map((k) => <button key={k} className="btn" onClick={() => runNow(k)}>Run {k} now</button>)}</div>}
        </section>
      </div>

      {admin && (
        <section className="card">
          <h2>Decisions</h2>
          {!props?.some((p) => p.status === "pending") && <Empty>Nothing waiting for your decision.</Empty>}
          {!props?.length ? null : props.map((p) => (
            <div key={p.id} className="prop">
              <div><strong>{p.title}</strong> <span className="muted small">· {p.kind} · {when(p.created_at)} · {p.status}</span></div>
              <div className="small">{p.detail}</div>
              {p.preview.length > 0 && (
                <details className="small"><summary>Preview ({p.count})</summary>
                  <table className="tbl"><tbody>{p.preview.map((r, i) => (
                    <tr key={i}>{Object.entries(r).filter(([k]) => k !== "tags").slice(0, 9).map(([k, v]) => <td key={k}><span className="muted">{k}</span> {String(v)}</td>)}</tr>
                  ))}</tbody></table>
                </details>
              )}
              {p.status === "pending" && <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                <button className="btn" onClick={() => decide(p.id, "approve")}>Approve</button>
                <button className="btn ghost" onClick={() => decide(p.id, "reject")}>Reject</button></div>}
            </div>
          ))}
        </section>
      )}

      {admin && <TagReview />}

      <section className="card">
        <h2>Runs</h2>
        {!s.runs.length ? <Empty>No runs yet.</Empty> : (
          <table className="tbl small">
            <thead><tr><th>#</th><th>Pipeline</th><th>Status</th><th>Started by</th><th>When</th><th>Cost</th><th>Steps</th></tr></thead>
            <tbody>{s.runs.map((r) => (
              <Fragment key={r.id}>
                <tr onClick={() => setOpen(open === r.id ? null : r.id)} style={{ cursor: "pointer" }}>
                  <td>{r.id}</td><td>{r.kind}</td><td className={r.status === "done" ? "good" : r.status === "failed" || r.status === "stopped" ? "bad" : ""}>{r.status}</td>
                  <td>{r.trigger}</td><td>{when(r.started_at || r.created_at)}</td><td>{usd(r.cost_usd)}</td>
                  <td>{r.steps.map((x) => <span key={x.agent} className={`chip ${x.status === "done" ? "" : "bad"}`}>{x.agent}</span>)}</td>
                </tr>
                {open === r.id && <tr><td colSpan={7}><pre className="mono small" style={{ whiteSpace: "pre-wrap", maxHeight: 320, overflow: "auto" }}>
                  {r.error ? `Stopped: ${r.error}\n\n` : ""}{r.steps.map((x) => `${x.agent} · ${x.status} · ${x.seconds ?? 0}s · ${usd(x.cost_usd ?? 0)}\n${x.error ? x.error + "\n" : ""}${JSON.stringify(x.result, null, 1)}`).join("\n\n")}
                </pre></td></tr>}
              </Fragment>
            ))}</tbody>
          </table>
        )}
      </section>

      {admin && (
        <section className="card">
          <h2>Employer job boards</h2>
          <p className="small muted">Read directly every day. Boards are also added automatically from posting URLs on Greenhouse, Lever and Ashby.</p>
          <table className="tbl small"><thead><tr><th>Company</th><th>Board</th><th>Last check</th></tr></thead>
            <tbody>{s.boards.map((x) => <tr key={x.ats + x.slug}><td>{x.company}</td><td className="mono">{x.ats}/{x.slug}</td>
              <td className={x.last_status.startsWith("failed") ? "bad" : ""}>{x.last_status || "not yet read"} {x.last_checked ? `· ${when(x.last_checked)}` : ""}</td></tr>)}</tbody></table>
          <form className="form" onSubmit={addBoard} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end", marginTop: 10 }}>
            <label>System<select value={board.ats} onChange={(e) => setBoard({ ...board, ats: e.target.value })}>
              <option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="ashby">Ashby</option></select></label>
            <label>Board name in URL<input value={board.slug} onChange={(e) => setBoard({ ...board, slug: e.target.value })} required /></label>
            <label>Company<input value={board.company} onChange={(e) => setBoard({ ...board, company: e.target.value })} /></label>
            <button className="btn">Add board</button>
          </form>
        </section>
      )}
    </>
  );
}
