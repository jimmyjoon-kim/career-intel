import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Empty, ErrorBox, PageHead, useFetch } from "../components";

type AutoHit = { source: string; phrase: string };
type RoleRev = {
  key: string; title: string; company: string; start: string; end: string; months: number; counted: boolean;
  families: string[]; auto: Record<string, AutoHit>; auto_team_size: number | null;
  final: Record<string, number>; team_size: number | null; reviewed: boolean; recency_weight: number;
};
type Payload = {
  qualifications: { group: string; tags: { tag: string; label: string }[] }[];
  roles: RoleRev[]; reviewed: number;
};

export default function Roles() {
  const { data, error, loading, setData } = useFetch<Payload>("/api/profile/roles");
  if (loading && !data) return <div className="muted">Loading…</div>;
  if (!data) return <ErrorBox msg={error} />;
  if (data.roles.length === 0) {
    return (
      <>
        <PageHead title="Role review" />
        <Empty>No roles could be read yet. <Link to="/profile">Paste your experience text</Link> first.</Empty>
      </>
    );
  }
  return (
    <>
      <PageHead
        title="Role review"
        sub={`${data.reviewed} of ${data.roles.length} roles reviewed. Each role starts with the qualifications its title, description and employer imply. Adjust anything that is wrong, then confirm.`}
      />
      <div className="notice small">
        Your confirmed values are what get scored. Role holders are scored from their own profile text with the same
        templates, so a qualification you add here and they did not write down will favour you slightly.
      </div>
      {data.roles.map((r) => <RoleCard key={r.key} role={r} quals={data.qualifications} onSaved={setData} />)}
    </>
  );
}

function RoleCard({ role, quals, onSaved }: { role: RoleRev; quals: Payload["qualifications"]; onSaved: (p: Payload) => void }) {
  const [vals, setVals] = useState<Record<string, number>>(role.final);
  const [team, setTeam] = useState(role.team_size?.toString() ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setVals(role.final); setTeam(role.team_size?.toString() ?? ""); }, [role]);

  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const tags: Record<string, number> = {};
      quals.forEach((g) => g.tags.forEach(({ tag }) => {
        const v = vals[tag] ?? 0;
        const auto = role.auto[tag] ? 1 : 0;
        if (v !== auto) tags[tag] = v;  // store only what you changed
      }));
      const p = await api<Payload>(`/api/profile/roles/${encodeURIComponent(role.key)}`, {
        method: "PUT", json: { tags, team_size: team === "" ? null : Number(team), confirmed: true },
      });
      onSaved(p);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <section className="card role-card">
      <div className="role-head">
        <div>
          <p className="eyebrow">{role.company}</p>
          <h2>{role.title}</h2>
          <p className="muted small">
            {role.start} – {role.end} · {role.months} months{role.counted ? "" : " · evidence only (not counted in years)"}
            {role.recency_weight < 1 ? " · ended over 8 years ago, counts half" : ""}
          </p>
          {role.families.length > 0 && <p className="small">Template: {role.families.join(" + ")}</p>}
        </div>
        <span className={`badge ${role.reviewed ? "ok" : ""}`}>{role.reviewed ? "Reviewed" : "Not reviewed"}</span>
      </div>
      <div className="qual-grid">
        {quals.map((g) => (
          <div key={g.group}>
            <h3>{g.group}</h3>
            {g.tags.map(({ tag, label }) => {
              const v = vals[tag] ?? 0;
              const a = role.auto[tag];
              return (
                <div key={tag} className="qual-row">
                  <div>
                    <div>{label}</div>
                    <div className="muted small">{a ? `${a.source}: ${a.phrase}` : "not found automatically"}</div>
                  </div>
                  <div className="seg" role="group" aria-label={label}>
                    {([[0, "No"], [0.5, "Partial"], [1, "Has"]] as const).map(([n, l]) => (
                      <button key={l} className={v === n ? `on m${n === 1 ? "1" : n === 0.5 ? "h" : "0"}` : ""} onClick={() => setVals({ ...vals, [tag]: n })}>{l}</button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div className="role-foot">
        <label>Team size you managed (people)
          <input type="number" min={0} value={team} placeholder={role.auto_team_size ? String(role.auto_team_size) : "e.g. 35"} onChange={(e) => setTeam(e.target.value)} />
        </label>
        <button className="btn primary" disabled={busy} onClick={save}>{role.reviewed ? "Save changes" : "Confirm role"}</button>
      </div>
      <ErrorBox msg={err} />
    </section>
  );
}
