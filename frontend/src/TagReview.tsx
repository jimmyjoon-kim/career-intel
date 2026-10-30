import { useState } from "react";
import { api } from "./api";
import { useFetch } from "./components";

type T = { tag: string; label: string };
type P = { id: number; company: string; title: string; url: string; test_split: boolean; agreed: T[]; disputed: T[] };
type R = { postings: P[]; remaining: number;
  reader_test: { test_postings: number; precision: number | null; recall: number | null; most_missed_tags: [string, number][]; labeled_postings: number } };

// Settle the requirement reader's disagreements. Settled postings become examples for the reader (4 of 5) or its test set (1 of 5).
export default function TagReview() {
  const { data, reload } = useFetch<R>("/api/agents/tag-review");
  const [sel, setSel] = useState<Record<number, Record<string, boolean>>>({});
  if (!data) return null;
  const t = data.reader_test;
  const val = (p: P, tag: string, def: boolean) => sel[p.id]?.[tag] ?? def;
  const toggle = (p: P, tag: string, def: boolean) => setSel({ ...sel, [p.id]: { ...(sel[p.id] ?? {}), [tag]: !val(p, tag, def) } });
  const save = async (p: P) => {
    const labels: Record<string, boolean> = {};
    p.agreed.forEach((x) => { labels[x.tag] = val(p, x.tag, true); });
    p.disputed.forEach((x) => { labels[x.tag] = val(p, x.tag, false); });
    await api(`/api/agents/tag-review/${p.id}`, { method: "POST", json: { labels } });
    reload();
  };
  return (
    <section className="card">
      <h2>Requirement tag review</h2>
      <p className="small muted">
        The reader reads each posting 3 times; these postings had disagreements. Tick every requirement the posting actually asks for, then save.
        Labeled postings: {t.labeled_postings}. Test set: {t.test_postings} posting{t.test_postings === 1 ? "" : "s"}
        {t.precision != null ? ` · reader precision ${Math.round(t.precision * 100)}%, recall ${Math.round((t.recall ?? 0) * 100)}%` : " · accuracy shows once test postings are labeled"}.
      </p>
      {data.postings.length === 0 ? <p className="small muted">Nothing to review.</p> : data.postings.slice(0, 8).map((p) => (
        <div key={p.id} className="prop">
          <div><strong>{p.company}</strong> — {p.title} {p.test_split && <span className="badge">test set</span>}{" "}
            <a className="small" href={p.url} target="_blank" rel="noreferrer">posting</a></div>
          <div className="chips" style={{ marginTop: 6 }}>
            {p.agreed.map((x) => <label key={x.tag} className="chip"><input type="checkbox" checked={val(p, x.tag, true)} onChange={() => toggle(p, x.tag, true)} /> {x.label}</label>)}
            {p.disputed.map((x) => <label key={x.tag} className="chip" style={{ outline: "1px dashed var(--warn)" }}><input type="checkbox" checked={val(p, x.tag, false)} onChange={() => toggle(p, x.tag, false)} /> {x.label} (disputed)</label>)}
          </div>
          <button className="btn" style={{ marginTop: 6 }} onClick={() => save(p)}>Save tags</button>
        </div>
      ))}
      {data.remaining > 8 && <p className="small muted">{data.remaining - 8} more after these.</p>}
    </section>
  );
}
