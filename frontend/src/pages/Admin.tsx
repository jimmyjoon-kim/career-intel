import { useState, type FormEvent } from "react";
import { api, upload } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, PageHead } from "../components";

export default function Admin() {
  const { status, refreshStatus } = useAuth();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [form, setForm] = useState({ company: "", title: "", url: "", location: "", remote_flag: "unstated", bay_area: false, pay_range: "", description: "" });

  const run = async (fn: () => Promise<string>) => {
    setBusy(true); setErr(null); setMsg(null);
    try { setMsg(await fn()); refreshStatus(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const onCsv = (f?: File) => f && run(async () => {
    const r = await upload<{ created: number; updated: number; skipped: number; chunks: number }>("/api/admin/import", f, { source_date: date });
    return `Imported: ${r.created} new, ${r.updated} updated, ${r.skipped} skipped. Index rebuilt (${r.chunks} chunks).`;
  });

  const addPosting = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const p = await api<{ company: string; title: string; tags: string[] }>("/api/admin/postings", { method: "POST", json: form });
      setForm({ ...form, company: "", title: "", url: "", description: "" });
      return `Added ${p.company} — ${p.title} with ${p.tags.length} requirement tags.`;
    });
  };

  return (
    <>
      <PageHead title="Data" sub="Shared market dataset. Admins only." />
      {msg && <div className="ok-box">{msg}</div>}
      <ErrorBox msg={err} />
      {status && (
        <section className="kpis">
          <div className="kpi"><div className="kpi-n">{status.postings}</div><div className="kpi-l">Postings</div></div>
          <div className="kpi"><div className="kpi-n">{status.chunks}</div><div className="kpi-l">Indexed chunks</div><div className="muted small">{status.embedding_model}</div></div>
          <div className="kpi"><div className="kpi-n">{status.llm ? "On" : "Off"}</div><div className="kpi-l">Claude</div><div className="muted small">{status.llm_model ?? "set ANTHROPIC_API_KEY"}</div></div>
        </section>
      )}
      <div className="grid2">
        <section className="card">
          <h2>Import weekly CSV</h2>
          <p className="muted small">The career-intel <span className="mono">postings_&lt;date&gt;.csv</span> format. Rows are matched by URL; existing rows are updated.</p>
          <label>Checked on<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
          <input type="file" accept=".csv" disabled={busy} onChange={(e) => onCsv(e.target.files?.[0])} />
          <hr />
          <h2>Rebuild index</h2>
          <p className="muted small">Re-embed every posting, market summary, method document and user CV. Run after changing the embedding provider.</p>
          <button className="btn" disabled={busy} onClick={() => run(async () => {
            const r = await api<{ chunks: number; users: number }>("/api/admin/reindex", { method: "POST" });
            return `Rebuilt ${r.chunks} chunks for ${r.users} users.`;
          })}>Rebuild</button>
        </section>
        <form className="card form" onSubmit={addPosting}>
          <h2>Add a posting</h2>
          <p className="muted small">Paste the job description; requirements are tagged automatically.</p>
          <label>Company<input required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></label>
          <label>Title<input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label>URL<input required type="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></label>
          <label>Location<input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></label>
          <label>Remote
            <select value={form.remote_flag} onChange={(e) => setForm({ ...form, remote_flag: e.target.value })}>
              <option value="unstated">Unstated</option><option value="yes">Remote</option><option value="hybrid">Hybrid</option><option value="no">On-site</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={form.bay_area} onChange={(e) => setForm({ ...form, bay_area: e.target.checked })} /> SF Bay Area</label>
          <label>Pay range<input value={form.pay_range} onChange={(e) => setForm({ ...form, pay_range: e.target.value })} /></label>
          <label>Job description<textarea rows={8} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <button className="btn primary" disabled={busy}>Add posting</button>
        </form>
      </div>
    </>
  );
}
