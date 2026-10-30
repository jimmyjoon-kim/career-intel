import { useEffect, useState } from "react";
import { api, upload, type Profile } from "./api";

type R = { profile?: Profile; note?: string } | Profile;

// Paste your LinkedIn link (read by the Mac task) or upload LinkedIn's PDF; review the result before it replaces anything.
export default function LinkedInImport({ prof, busy, run }: { prof: Profile; busy: boolean; run: (fn: () => Promise<R>, ok: string) => void }) {
  const [url, setUrl] = useState(prof.linkedin_url);
  useEffect(() => setUrl(prof.linkedin_url), [prof.linkedin_url]);
  const imp = prof.linkedin_import || {};
  return (
    <section className="card">
      <h2>LinkedIn profile</h2>
      <p className="muted small">Paste your profile link and the app pulls your experience and education. It is used together with your CV, never in place of it: CV roles stay as the base, LinkedIn adds detail to matching roles and any roles your CV leaves out. Nothing is used until you apply it.</p>
      <div className="form" style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "flex-end" }}>
        <input style={{ flex: 1, minWidth: 260 }} value={url} placeholder="https://www.linkedin.com/in/your-name" onChange={(e) => setUrl(e.target.value)} />
        <button className="btn primary" disabled={busy || url.trim().length < 20}
          onClick={() => run(() => api<R>("/api/profile/linkedin", { method: "POST", json: { url } }), "")}>Pull from LinkedIn</button>
      </div>
      <p className="muted small" style={{ marginBottom: 4 }}>
        Faster: on your LinkedIn profile choose More → Save to PDF, then upload it here.{" "}
        <input type="file" accept=".pdf" disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => upload<R>("/api/profile/linkedin/pdf", f), ""); }} />
      </p>
      {imp.status === "requested" && <div className="small">Waiting for the next read by the task on your Mac (requested {imp.requested_at?.slice(0, 10)}).</div>}
      {imp.status === "applied" && (
        <div className="small">
          <span className="good">In use with your CV</span> · read {imp.read_at} from {imp.source === "pdf" ? "LinkedIn PDF" : "your profile link"} · {imp.roles} roles
          {imp.merge && <> · {imp.merge.matched} matched to CV roles ({imp.merge.lines_added} new detail lines), {imp.merge.added} added</>}{" "}
          <button className="btn ghost" disabled={busy} onClick={() => run(() => api<R>("/api/profile/linkedin", { method: "DELETE" }), "")}>Stop using LinkedIn</button>
        </div>
      )}
      {imp.status === "ready" && (
        <div className="prop">
          <b>Import ready for review</b> <span className="small muted">· {imp.roles} roles · {imp.source === "pdf" ? "LinkedIn PDF" : "profile link"} · read {imp.read_at}</span>
          <textarea rows={10} readOnly value={imp.experience_text} />
          {imp.education_text && <details><summary className="small">Education read</summary><pre className="small" style={{ whiteSpace: "pre-wrap" }}>{imp.education_text}</pre></details>}
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn primary" disabled={busy} onClick={() => run(() => api<R>("/api/profile/linkedin/apply", { method: "POST" }), "")}>
              Apply: use with my CV</button>
            <button className="btn ghost" disabled={busy} onClick={() => run(() => api<R>("/api/profile/linkedin/import", { method: "DELETE" }), "Import discarded.")}>Discard</button>
          </div>
        </div>
      )}
    </section>
  );
}
