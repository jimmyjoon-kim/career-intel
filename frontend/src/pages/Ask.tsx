import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Answer } from "../api";
import { ErrorBox, PageHead } from "../components";

const SUGGESTIONS = [
  "Which open roles fit me best, and what are the hard gaps on each?",
  "What would my score be if my level were read as VP instead of C-level?",
  "Which of my gaps are closable before I move, and how much would each move my score?",
  "What did the agents find this week, and is anything waiting for my approval?",
];

const TOOL_LABEL: Record<string, string> = {
  get_scorecard: "scorecard", what_if: "what-if", search_postings: "postings", get_market_requirements: "market requirements",
  search_documents: "documents", get_agent_status: "agent team", get_score_history: "score history", number_check: "number check",
  find_new_postings: "new search started", get_profile_settings: "your settings",
};

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
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [items.length, busy]);

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
      <PageHead title="Ask" sub="An agent answers from your scorecard, what-if rescoring, live postings, market requirements, your documents and the agent team. Every number comes from those lookups." />
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
              {a.mode === "extractive" && <div className="muted small">Offline mode — sources only</div>}
              {a.steps && a.steps.length > 0 && (
                <div className="chips" style={{ marginBottom: 8 }} title="What the agent looked up">
                  {a.steps.map((s, k) => (
                    <span key={k} className="chip-d acc" title={JSON.stringify(s.input)}>
                      {TOOL_LABEL[s.tool] ?? s.tool}{s.tool === "what_if" ? `: ${Object.entries((s.input as { changes?: Record<string, number> }).changes ?? {}).map(([f, v]) => `${f}=${v}`).join(", ")}` : ""}
                    </span>
                  ))}
                </div>
              )}
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
        {busy && <div className="muted">The agent is looking things up…</div>}
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
