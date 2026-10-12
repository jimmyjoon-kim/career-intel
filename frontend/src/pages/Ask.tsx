import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Answer } from "../api";
import { ErrorBox, PageHead } from "../components";

const SUGGESTIONS = [
  "Which open roles fit me best, and what are the hard gaps on each?",
  "What do Partnerships roles require that I do not yet evidence?",
  "Which of my gaps are closable before I move?",
  "What pay ranges are posted for Director-level ad sales roles?",
];

function renderAnswer(text: string) {
  return text.split("\n").map((line, i) => (
    <p key={i}>
      {line.split(/(\[\d+\])/g).map((part, j) => /^\[\d+\]$/.test(part) ? <sup key={j} className="cite">{part}</sup> : part)}
    </p>
  ));
}

export default function Ask() {
  const [items, setItems] = useState<Answer[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api<Answer[]>("/api/ask/history").then((h) => setItems(h.reverse())).catch(() => {}); }, []);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [items.length, busy]);

  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true); setErr(null); setQ("");
    try {
      const r = await api<Answer>("/api/ask", { method: "POST", json: { question } });
      setItems((xs) => [...xs, { ...r, question }]);
    } catch (e) { setErr((e as Error).message); setQ(question); } finally { setBusy(false); }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); ask(q); };

  return (
    <div className="ask">
      <PageHead title="Ask" sub="Answers come only from cited sources: postings, market statistics, the method, your CV and your scorecard." />
      <div className="thread">
        {items.length === 0 && (
          <div className="suggest">
            {SUGGESTIONS.map((s) => <button key={s} className="chip-btn" onClick={() => ask(s)}>{s}</button>)}
          </div>
        )}
        {items.map((a, i) => (
          <div key={a.id ?? i} className="qa">
            <div className="q">{a.question}</div>
            <div className="a card">
              {a.mode !== "llm" && <div className="muted small">{a.mode === "extractive" ? "Offline mode — sources only" : ""}</div>}
              {renderAnswer(a.answer)}
              {a.sources.length > 0 && (
                <details className="sources">
                  <summary className="small">{a.sources.length} sources</summary>
                  <ol>
                    {a.sources.map((s) => (
                      <li key={s.n}>
                        <span className="badge">{s.type}</span>{" "}
                        {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> : s.title}
                        <div className="muted small">{s.excerpt}</div>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="muted">Searching sources…</div>}
        <div ref={endRef} />
      </div>
      <ErrorBox msg={err} />
      <form className="ask-bar" onSubmit={submit}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about roles, requirements or your gaps" disabled={busy} />
        <button className="btn primary" disabled={busy || q.trim().length < 3}>Ask</button>
      </form>
    </div>
  );
}
