import { useState, type FormEvent } from "react";
import { api } from "./api";
import { useFetch } from "./components";

const FAM_KEY = "ci_family";
const savedFamily = () => { try { return localStorage.getItem(FAM_KEY) || "Partnerships"; } catch { return "Partnerships"; } };

// The role you are assessed as: shared by Scorecard and Gate & gaps (remembered in this browser).
export function useFamily(): [string, (k: string) => void] {
  const [family, setFamilyState] = useState(savedFamily);
  const setFamily = (k: string) => { setFamilyState(k); try { localStorage.setItem(FAM_KEY, k); } catch { /* storage unavailable */ } };
  return [family, setFamily];
}

export type Fam = { key: string; label: string; custom: boolean; holders: number; waiting: number; postings: number;
  state: "ready" | "awaiting_approval" | "requested" | "provisional" };

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
            {f.label} <span className="small muted">· {f.state === "ready" ? `${f.holders} peers` : f.state === "awaiting_approval" ? `${f.waiting} peers to approve` : f.state === "requested" ? "collecting peers automatically" : "postings only"}</span>
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
  request: { status: string; requested_at: string; position: number | null; queue: number } | null;
  requirements: { tag: string; label: string; share: number; match: number; closable: boolean }[];
  gaps: { tag: string; label: string; share: number; match: number; closable: boolean }[];
  top_postings: { id: number; company: string; title: string; location: string; url: string; match: number; passes: boolean; outside: string[] }[];
};

// Until a role has a group of holders: what its open postings require, your match, and your best postings.
export function ProvisionalView({ fam, onRequest }: { fam: string; onRequest: () => void }) {
  const { data } = useFetch<Prov>(`/api/scorecard/provisional?family=${encodeURIComponent(fam)}`);
  const { data: fl } = useFetch<{ families: Fam[] }>("/api/scorecard/families");
  const [sent, setSent] = useState(false);
  const [approving, setApproving] = useState<string | null>(null);
  const waiting = fl?.families.find((f) => f.key === fam)?.waiting ?? 0;
  const approve = async () => {
    setApproving("Approving…");
    const r = await api<{ holders_added: number; holders_now: number }>("/api/scorecard/families/approve", { method: "POST", json: { family: fam } });
    setApproving(`${r.holders_added} peers added (${r.holders_now} in total). Reloading the full scorecard…`);
    setTimeout(() => window.location.reload(), 1200);
  };
  if (!data) return <div className="muted">Loading…</div>;
  void onRequest; void sent; void setSent;
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
          {waiting > 0 && (
            <div className="prop" style={{ borderColor: "var(--accent)" }}>
              <b>{waiting} peers collected and waiting for your approval.</b>
              <div className="small" style={{ margin: "4px 0" }}>Screened on arrival: no names or profile links kept, only people with dated roles, no duplicates. Approving builds the full scorecard for this role.</div>
              {approving ? <div className="small good">{approving}</div> : <button className="btn primary" onClick={approve}>Approve {waiting} peers and build the scorecard</button>}
              <div className="small muted">Or review each batch on the Agents page.</div>
            </div>
          )}
          <p className="small muted">Peers approved so far: {data.holders}. The full scorecard (percentile among holders, factor comparison, focus plan) appears once enough holders are collected and you approve them on the Agents page.</p>
          <div className="small good">
            Collecting peers for this role automatically{data.request?.requested_at ? ` (queued ${data.request.requested_at.slice(0, 10)})` : ""}.
            {" "}The research task on your Mac runs every hour at :40 KST and collects every queued role; peers are screened and added
            on arrival, and the full scorecard replaces this view once 20 are in.
          </div>
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
