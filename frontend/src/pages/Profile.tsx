import { useEffect, useMemo, useState } from "react";
import { api, upload, type Profile } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, PageHead, useFetch } from "../components";

type Tax = { levels: string[]; tags: { key: string; label: string; group: string; closable: boolean }[] };
const GROUPS = ["function", "domain", "management", "skill", "education"];

export default function ProfilePage() {
  const { data: prof, setData: setProf, error } = useFetch<Profile>("/api/profile");
  const { data: tax } = useFetch<Tax>("/api/profile/taxonomy");
  const { refreshStatus } = useAuth();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cvDraft, setCvDraft] = useState("");
  const [expDraft, setExpDraft] = useState("");
  const [target, setTarget] = useState("");
  const [prefs, setPrefs] = useState({ min_level: "Director", locations: "", remote_ok: true, needs_sponsorship: false, excluded: "", years: "" });

  useEffect(() => {
    if (!prof) return;
    setCvDraft(prof.cv_text);
    setExpDraft(prof.experience_text);
    setTarget(prof.target_date);
    setPrefs({
      min_level: prof.min_level, locations: prof.locations.join(", "), remote_ok: prof.remote_ok,
      needs_sponsorship: prof.needs_sponsorship, excluded: prof.excluded_title_terms.join(", "),
      years: prof.years_experience?.toString() ?? "",
    });
  }, [prof]);

  const run = async (fn: () => Promise<{ profile?: Profile } | Profile>, ok: string) => {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await fn();
      setProf("profile" in r && r.profile ? r.profile : (r as Profile));
      setMsg(ok);
      refreshStatus();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const onFile = (f: File | undefined) => f && run(async () => {
    const r = await upload<{ profile: Profile; extraction_mode: string; tags_found: number }>("/api/profile/cv", f);
    setMsg(`${r.tags_found} requirements found (${r.extraction_mode === "llm" ? "read by Claude" : "keyword matching"}).`);
    return r;
  }, "CV processed.");

  const savePrefs = () => run(() => api("/api/profile", {
    method: "PUT",
    json: {
      min_level: prefs.min_level,
      locations: prefs.locations.split(",").map((s) => s.trim()).filter(Boolean),
      remote_ok: prefs.remote_ok, needs_sponsorship: prefs.needs_sponsorship,
      excluded_title_terms: prefs.excluded.split(",").map((s) => s.trim()).filter(Boolean),
      years_experience: prefs.years ? Number(prefs.years) : undefined,
    },
  }), "Preferences saved.");

  const saveCvText = () => run(() => api("/api/profile", { method: "PUT", json: { cv_text: cvDraft } }), "CV text processed.");

  const saveExperience = () => run(() => api("/api/profile", { method: "PUT", json: { experience_text: expDraft, target_date: target } }),
    "Experience saved. Your scorecard has been recalculated.");

  const setTag = (tag: string, match: number, evidence: string) =>
    run(() => api(`/api/profile/tags/${tag}`, { method: "PUT", json: { match, evidence } }), "Saved.");

  const grouped = useMemo(() => {
    const g: Record<string, Tax["tags"]> = {};
    (tax?.tags ?? []).forEach((t) => (g[t.group] ||= []).push(t));
    return g;
  }, [tax]);

  if (!prof) return <ErrorBox msg={error} />;
  const found = Object.keys(prof.tag_matches).length;

  return (
    <>
      <PageHead title="Profile" sub="Your evidence and your gate. Scores update everywhere when you save." />
      {msg && <div className="ok-box">{msg}</div>}
      <ErrorBox msg={err} />

      <div className="grid2">
        <section className="card">
          <h2>CV</h2>
          <p className="muted small">PDF, DOCX or TXT, up to 5 MB. Your CV is private to your account.</p>
          <input type="file" accept=".pdf,.docx,.txt,.md" disabled={busy} onChange={(e) => onFile(e.target.files?.[0])} />
          <details>
            <summary className="small">Or paste / edit the text</summary>
            <textarea rows={10} value={cvDraft} onChange={(e) => setCvDraft(e.target.value)} />
            <button className="btn" disabled={busy || cvDraft.trim().length < 200} onClick={saveCvText}>Process text</button>
          </details>
          <p className="muted small">{prof.cv_text ? `${prof.cv_text.length.toLocaleString()} characters on file · ${found} requirements evidenced` : "No CV on file."}</p>
        </section>

        <section className="card">
          <h2>Gate preferences</h2>
          <div className="form">
            <label>Minimum level
              <select value={prefs.min_level} onChange={(e) => setPrefs({ ...prefs, min_level: e.target.value })}>
                {(tax?.levels ?? []).map((l) => <option key={l}>{l}</option>)}
              </select>
            </label>
            <label>Locations <span className="muted small">(comma-separated; "SF Bay Area" matches the whole region)</span>
              <input value={prefs.locations} onChange={(e) => setPrefs({ ...prefs, locations: e.target.value })} />
            </label>
            <label>Excluded title terms <span className="muted small">(comma-separated)</span>
              <input value={prefs.excluded} placeholder="e.g. Country Manager" onChange={(e) => setPrefs({ ...prefs, excluded: e.target.value })} />
            </label>
            <label>Years of experience
              <input type="number" min={0} max={50} value={prefs.years} onChange={(e) => setPrefs({ ...prefs, years: e.target.value })} />
            </label>
            <label className="check"><input type="checkbox" checked={prefs.remote_ok} onChange={(e) => setPrefs({ ...prefs, remote_ok: e.target.checked })} /> Remote roles are acceptable</label>
            <label className="check"><input type="checkbox" checked={prefs.needs_sponsorship} onChange={(e) => setPrefs({ ...prefs, needs_sponsorship: e.target.checked })} /> I need visa sponsorship</label>
            <button className="btn primary" disabled={busy} onClick={savePrefs}>Save preferences</button>
          </div>
        </section>
      </div>

      <section className="card">
        <h2>Full experience text</h2>
        <p className="muted small">
          Used for your Scorecard. On LinkedIn open Experience, then Show all; select the whole list and paste it here. CV-style text with
          dates on each role line also works. Every role description is read, not only titles. If this is empty, your CV text is used.
        </p>
        <textarea rows={12} value={expDraft} placeholder={"Interim CRO\nWortal.AI\nJan 2025 - Jan 2026 · 1 yr 1 mo\n..."} onChange={(e) => setExpDraft(e.target.value)} />
        <div className="form">
          <label>Target application date <span className="muted small">(YYYY-MM; marks which gaps can close in time)</span>
            <input value={target} placeholder="2027-06" onChange={(e) => setTarget(e.target.value)} />
          </label>
          <button className="btn primary" disabled={busy} onClick={saveExperience}>Save and rescore</button>
          <p className="muted small">Next: <a href="/roles">review each role</a> and confirm its qualifications.</p>
        </div>
      </section>

      <section className="card">
        <h2>Evidence by requirement</h2>
        <p className="muted small">Set each requirement to Has, Partial or Missing. Your choices override what was read from the CV.</p>
        {GROUPS.map((g) => grouped[g] && (
          <div key={g} className="tag-group">
            <h3>{g[0].toUpperCase() + g.slice(1)}</h3>
            {grouped[g].map((t) => <TagRowEditor key={t.key} t={t} m={prof.tag_matches[t.key]} busy={busy} onSave={setTag} />)}
          </div>
        ))}
      </section>
    </>
  );
}

function TagRowEditor({ t, m, busy, onSave }: {
  t: { key: string; label: string }; m?: { match: number; evidence: string; source: string }; busy: boolean;
  onSave: (tag: string, match: number, evidence: string) => void;
}) {
  const value = m?.match ?? 0;
  const [ev, setEv] = useState(m?.evidence ?? "");
  useEffect(() => setEv(m?.evidence ?? ""), [m?.evidence]);
  return (
    <div className="tag-row">
      <div className="tag-name">
        {t.label}
        {m?.source === "user" && <span className="badge">You set</span>}
      </div>
      <div className="seg" role="group" aria-label={t.label}>
        {[[0, "Missing"], [0.5, "Partial"], [1, "Has"]].map(([v, l]) => (
          <button key={l} disabled={busy} className={value === v ? `on m${v === 1 ? "1" : v === 0.5 ? "h" : "0"}` : ""} onClick={() => onSave(t.key, v as number, ev)}>{l}</button>
        ))}
      </div>
      <input className="ev" placeholder="Evidence" value={ev} onChange={(e) => setEv(e.target.value)}
        onBlur={() => ev !== (m?.evidence ?? "") && onSave(t.key, value, ev)} />
    </div>
  );
}
