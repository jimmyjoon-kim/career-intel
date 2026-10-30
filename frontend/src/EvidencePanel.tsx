import { useState } from "react";
import { api } from "./api";
import { useFetch } from "./components";

type Sug = { id: number; tag: string; label: string; match: number; quote: string; source: string; postings: number; status: string };

// Lines from your own documents that may evidence requirements postings ask for. Nothing changes until you confirm.
export default function EvidencePanel() {
  const { data, reload } = useFetch<Sug[]>("/api/profile/evidence");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const pending = (data ?? []).filter((s) => s.status === "pending");
  const done = (data ?? []).filter((s) => s.status !== "pending");

  const find = async () => {
    setBusy(true); setNote(null);
    try {
      const r = await api<{ checked?: number; suggested?: number; skipped?: string; stopped?: string }>("/api/profile/evidence/find", { method: "POST" });
      setNote(r.skipped ? `Not run: ${r.skipped}.` : r.stopped ? r.stopped : `Checked ${r.checked ?? 0} requirements; ${r.suggested ?? 0} new suggestions.`);
      reload();
    } catch (e) { setNote((e as Error).message); } finally { setBusy(false); }
  };
  const decide = async (id: number, confirm: boolean) => {
    const r = await api<{ score: number | null }>(`/api/profile/evidence/${id}`, { method: "POST", json: { confirm } });
    setNote(confirm ? `Confirmed.${r.score != null ? ` Score now ${r.score}.` : ""}` : "Rejected.");
    reload();
  };

  return (
    <section className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Evidence from your documents</h2>
        <button className="btn" disabled={busy} onClick={find}>{busy ? "Searching…" : "Find evidence now"}</button>
      </div>
      <p className="small muted">Requirements that open postings ask for and your profile does not yet show. Each line below is quoted from your own text; confirm only what is accurate. Also runs every Monday.</p>
      {note && <div className="small">{note}</div>}
      {pending.length === 0 ? <p className="small muted">Nothing to confirm.</p> : pending.map((s) => (
        <div key={s.id} className="prop">
          <div><strong>{s.label}</strong> <span className="muted small">· asked by {s.postings} posting{s.postings === 1 ? "" : "s"} · {s.match >= 1 ? "clear" : "partial"}</span></div>
          <blockquote className="small" style={{ margin: "6px 0", paddingLeft: 10, borderLeft: "3px solid var(--line)" }}>“{s.quote}”</blockquote>
          <div className="small muted">{s.source}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            <button className="btn" onClick={() => decide(s.id, true)}>Confirm</button>
            <button className="btn ghost" onClick={() => decide(s.id, false)}>Not accurate</button>
          </div>
        </div>
      ))}
      {done.length > 0 && <details className="small"><summary>{done.length} decided</summary>
        <ul>{done.map((s) => <li key={s.id}>{s.label}: {s.status}</li>)}</ul></details>}
    </section>
  );
}
