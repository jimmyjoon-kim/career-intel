import { useState, type FormEvent } from "react";
import { api } from "./api";
import { useFetch } from "./components";

export type Fam = { key: string; label: string; custom: boolean; holders: number; postings: number; state: "ready" | "requested" | "provisional" };

// Pick the role you want to be assessed against; name any other role to add it.
export function FamilyBar({ value, onChange }: { value: string; onChange: (k: string) => void }) {
  const { data, reload } = useFetch<{ families: Fam[]; ready_at: number }>("/api/scorecard/families");
  const [name, setName] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (name.trim().length < 3) return;
    const r = await api<{ family: string; note: string }>("/api/scorecard/families", { method: "POST", json: { name } });
    setNote(r.note); setName(""); reload(); onChange(r.family);
  };
  return (
    <section className="tile" style={{ padding: "10px 14px" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        <span className="small muted" style={{ marginRight: 4 }}>Assess me as:</span>
        {(data?.families ?? []).map((f) => (
          <button key={f.key} className={`chip-btn ${value === f.key ? "on" : ""}`} onClick={() => onChange(f.key)}
            style={value === f.key ? { borderColor: "var(--accent)", color: "var(--accent)" } : undefined}
            title={`${f.holders} role holders · ${f.postings} open postings`}>
            {f.label} <span className="small muted">· {f.state === "ready" ? `${f.holders} peers` : f.state === "requested" ? "collecting peers" : "postings only"}</span>
          </button>
        ))}
        <form onSubmit={add} style={{ display: "flex", gap: 6 }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Other role, e.g. Head of Developer Relations" style={{ minWidth: 240 }} />
          <button className="btn">Add</button>
        </form>
      </div>
      {note && <div className="small" style={{ marginTop: 6 }}>{note}</div>}
    </section>
  );
}

type Prov = {
  family: string; postings: number; holders: number; fit: number | null; note?: string;
  requirements: { tag: string; label: string; share: number; match: number; closable: boolean }[];
  gaps: { tag: string; label: string; share: number; match: number; closable: boolean }[];
  top_postings: { id: number; company: string; title: string; location: string; url: string; match: number; passes: boolean; outside: string[] }[];
};

// Until a role has a group of holders: what its open postings require, your match, and your best postings.
export function ProvisionalView({ fam, onRequest }: { fam: string; onRequest: () => void }) {
  const { data } = useFetch<Prov>(`/api/scorecard/provisional?family=${encodeURIComponent(fam)}`);
  const [sent, setSent] = useState(false);
  if (!data) return <div className="muted">Loading…</div>;
  const request = async () => { await api("/api/scorecard/families", { method: "POST", json: { name: fam } }); setSent(true); onRequest(); };
  return (
    <>
      <section className="sc-row2">
        <div className="tile">
          <span className="kick warn">Provisional · no peer group yet</span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, margin: "6px 0" }}>
            <span style={{ fontSize: 40, fontWeight: 800 }}>{data.fit ?? "—"}{data.fit != null && <span className="small">%</span>}</span>
            <span className="small">fit on the requirements of {data.postings} open postings</span>
          </div>
          <p className="small">{data.note ?? "No open postings match this role yet."}</p>
          <p className="small muted">Peers collected so far: {data.holders}. The full scorecard (percentile among holders, factor comparison, focus plan) appears once enough holders are collected and you approve them on the Agents page.</p>
          {!sent && <button className="btn" onClick={request}>Collect peers for this role</button>}
          {sent && <div className="small good">Requested. The hire-research task on your Mac picks it up.</div>}
        </div>
        <div className="tile">
          <span className="tile-title">What these postings require · your match</span>
          {data.requirements.length === 0 ? <p className="small muted">No tagged requirements yet.</p> : data.requirements.map((r) => (
            <div key={r.tag} className="fac" style={{ gridTemplateColumns: "minmax(0,1fr) 120px 70px", cursor: "inherit" }}>
              <span className="small">{r.label}</span>
              <span className="track"><span className="fill" style={{ width: `${Math.round(100 * r.share)}%`, background: r.match >= 1 ? "var(--good)" : r.match > 0 ? "var(--warn)" : "var(--bad)" }} /></span>
              <span className="small" style={{ textAlign: "right" }}>{Math.round(100 * r.share)}% · {r.match >= 1 ? "have" : r.match > 0 ? "partial" : "missing"}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="tile">
        <span className="tile-title">Best postings for you in this role</span>
        {data.top_postings.map((p) => (
          <div key={p.id} className="prop" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <span><b>{p.company}</b> — {p.title} <span className="small muted">· {p.location}</span>{" "}
              <a className="small" href={p.url} target="_blank" rel="noreferrer">posting</a>
              {!p.passes && p.outside.length > 0 && <div className="chips" style={{ marginTop: 4 }}>{p.outside.map((o) => <span key={o} className="chip-d warn">{o}</span>)}</div>}
            </span>
            <b>{p.match}%</b>
          </div>
        ))}
        {data.gaps.length > 0 && <p className="small" style={{ marginBottom: 0 }}><b>Most common requirements you do not fully show:</b> {data.gaps.map((g) => `${g.label} (${Math.round(100 * g.share)}%)`).join("; ")}</p>}
      </section>
    </>
  );
}
