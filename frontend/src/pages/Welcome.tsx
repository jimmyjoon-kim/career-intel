import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, upload, type Profile } from "../api";
import { ErrorBox, PageHead, useFetch } from "../components";
import LinkedInImport from "../LinkedInImport";

type Tax = { levels: string[]; families: string[]; sectors: Record<string, string>; markets: Record<string, string> };
type Auth = "authorized" | "needs_sponsorship" | "";
const list = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

/** Set-up: the answers every score depends on. Shown after sign-up; can be reopened from Profile. */
export default function Welcome() {
  const nav = useNavigate();
  const { data: prof, setData: setProf, error } = useFetch<Profile>("/api/profile");
  const { data: tax } = useFetch<Tax>("/api/profile/taxonomy");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cv, setCv] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [otherRoles, setOtherRoles] = useState("");
  const [level, setLevel] = useState("Director");
  const [locations, setLocations] = useState("");
  const [remote, setRemote] = useState(true);
  const [relocating, setRelocating] = useState(false);
  const [target, setTarget] = useState("");
  const [auth, setAuth] = useState<Record<string, Auth>>({});
  const [sectors, setSectors] = useState<string[]>([]);
  const [companies, setCompanies] = useState("");
  const [noCountry, setNoCountry] = useState(false);
  const [excluded, setExcluded] = useState("");

  useEffect(() => {
    if (!prof || !tax) return;
    setCv(prof.cv_text);
    setRoles(prof.target_roles.filter((r) => tax.families.includes(r)));
    setOtherRoles(prof.target_roles.filter((r) => !tax.families.includes(r)).join(", "));
    setLevel(prof.min_level); setLocations(prof.locations.join(", ")); setRemote(prof.remote_ok);
    setRelocating(prof.relocating); setTarget(prof.target_date); setAuth(prof.work_auth || {});
    setSectors(prof.target_industries); setCompanies(prof.target_companies.join(", "));
    setNoCountry(prof.exclude_country_scope); setExcluded(prof.excluded_title_terms.join(", "));
  }, [prof, tax]);

  const run = async <R,>(fn: () => Promise<R>, ok: string) => {
    setBusy(true); setErr(null); setMsg(null);
    try { await fn(); setMsg(ok); setProf(await api<Profile>("/api/profile")); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const toggle = (arr: string[], v: string, set: (x: string[]) => void) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const allRoles = [...roles, ...list(otherRoles)];
  const missing = [!(prof?.cv_text || cv.trim()) && "your CV", allRoles.length === 0 && "at least one target role",
                   list(locations).length === 0 && !remote && "a location or remote"].filter(Boolean) as string[];

  const save = () => run(async () => {
    await api("/api/profile", { method: "PUT", json: {
      ...(cv.trim() && cv.trim() !== prof?.cv_text ? { cv_text: cv.trim() } : {}),
      target_roles: allRoles, min_level: level, locations: list(locations), remote_ok: remote, relocating,
      target_date: target, work_auth: Object.fromEntries(Object.entries(auth).filter(([, v]) => v)),
      needs_sponsorship: Object.values(auth).includes("needs_sponsorship"),
      target_industries: sectors, target_companies: list(companies), exclude_country_scope: noCountry,
      excluded_title_terms: list(excluded), onboarded: true } });
    nav("/");
  }, "Saved. Postings and role holders for your roles are being collected now.");

  if (error) return <ErrorBox msg={error} />;
  if (!prof || !tax) return <div className="muted">Loading…</div>;
  return (
    <>
      <PageHead title="Set up your assessment" sub="Your answers decide who you are compared with and which jobs count. Every answer can be changed later under Profile." />
      {msg && <div className="callout">{msg}</div>}
      {err && <div className="error">{err}</div>}

      <section className="card">
        <h2>1. Your CV <span className="muted small">(required)</span></h2>
        <p className="muted small">Upload a PDF or Word file, or paste the text. Roles, dates, education and achievements are read from it.</p>
        <input type="file" accept=".pdf,.doc,.docx,.txt" disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => upload("/api/profile/cv", f), "CV read."); }} />
        <textarea rows={6} value={cv} onChange={(e) => setCv(e.target.value)} placeholder="…or paste your CV text" />
        {prof.cv_text && <p className="small good">CV on file ({prof.cv_text.length.toLocaleString()} characters).</p>}
      </section>

      <section className="card">
        <h2>2. LinkedIn <span className="muted small">(optional, used together with the CV)</span></h2>
        <LinkedInImport prof={prof} busy={busy} run={run} />
      </section>

      <section className="card">
        <h2>3. Roles you are targeting</h2>
        <p className="muted small">You are compared with people who hold these roles. Pick any, and type others (for example "Head of Product", "Director of Engineering").</p>
        <div className="chips">{tax.families.map((f) => (
          <label key={f} className="chip"><input type="checkbox" checked={roles.includes(f)} onChange={() => toggle(roles, f, setRoles)} /> {f}</label>))}</div>
        <input value={otherRoles} onChange={(e) => setOtherRoles(e.target.value)} placeholder="Other roles, comma-separated" />
        <label>Lowest level you would accept
          <select value={level} onChange={(e) => setLevel(e.target.value)}>{tax.levels.map((l) => <option key={l}>{l}</option>)}</select></label>
      </section>

      <section className="card">
        <h2>4. Where</h2>
        <label>Locations <span className="muted small">(cities, countries or regions such as "APAC" or "Europe"; empty = anywhere)</span>
          <input value={locations} onChange={(e) => setLocations(e.target.value)} placeholder="e.g. San Francisco Bay Area, London, Singapore" /></label>
        <label className="row"><input type="checkbox" checked={remote} onChange={(e) => setRemote(e.target.checked)} /> Remote roles are fine</label>
        <label className="row"><input type="checkbox" checked={relocating} onChange={(e) => setRelocating(e.target.checked)} /> I am relocating to one of these locations</label>
        <label>Target start month <span className="muted small">(gaps are marked closable or not by this date)</span>
          <input type="month" value={target} onChange={(e) => setTarget(e.target.value)} /></label>
        <h3>Work authorization</h3>
        <p className="muted small">For each market you are targeting. Jobs that state they do not sponsor visas are screened out only where you need sponsorship.</p>
        {Object.entries(tax.markets).map(([k, label]) => (
          <label key={k}>{label}
            <select value={auth[k] || ""} onChange={(e) => setAuth({ ...auth, [k]: e.target.value as Auth })}>
              <option value="">Not targeting / not stated</option>
              <option value="authorized">Authorized to work (citizen, permanent resident or valid visa)</option>
              <option value="needs_sponsorship">Would need visa sponsorship</option>
            </select></label>))}
      </section>

      <section className="card">
        <h2>5. Industries and companies</h2>
        <div className="chips">{Object.entries(tax.sectors).map(([k, label]) => (
          <label key={k} className="chip"><input type="checkbox" checked={sectors.includes(k)} onChange={() => toggle(sectors, k, setSectors)} /> {label}</label>))}</div>
        <label>Companies to watch <span className="muted small">(optional; their open roles are searched)</span>
          <input value={companies} onChange={(e) => setCompanies(e.target.value)} placeholder="e.g. Stripe, Spotify, Grab" /></label>
      </section>

      <section className="card">
        <h2>6. Exclusions</h2>
        <label className="row"><input type="checkbox" checked={noCountry} onChange={(e) => setNoCountry(e.target.checked)} /> Leave out single-country roles and Country Manager titles</label>
        <label>Title words to exclude <span className="muted small">(comma-separated)</span>
          <input value={excluded} onChange={(e) => setExcluded(e.target.value)} placeholder="e.g. intern, contract" /></label>
      </section>

      {missing.length > 0 && <p className="small bad">Still needed: {missing.join(", ")}.</p>}
      <button className="btn primary" disabled={busy || missing.length > 0} onClick={save}>Save and see my assessment</button>
    </>
  );
}
