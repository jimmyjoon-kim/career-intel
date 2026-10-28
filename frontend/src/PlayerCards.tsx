import { useState } from "react";
import type { PlayerCard } from "./api";

const tierOf = (ovr: number | null) => (ovr == null ? "t3" : ovr >= 75 ? "t1" : ovr >= 60 ? "t2" : "t3");
const initials = (name: string) => name.split(/[\s·.]+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

export function PCard({ c, size = "sm", onClick, you = false }: { c: PlayerCard; size?: "lg" | "sm"; onClick?: () => void; you?: boolean }) {
  const body = (
    <>
      <div className="pc-top">
        <div className="pc-ovr">
          <span className="pc-num">{c.ovr ?? "—"}</span>
          <span className="pc-pos">{c.position}</span>
        </div>
        {c.photo
          ? <img className="pc-photo" src={c.photo} alt="Your profile photo" />
          : <div className="pc-mono" aria-hidden="true">{you ? "YOU" : initials(c.name)}</div>}
      </div>
      <div className="pc-name">{c.name}</div>
      <div className="pc-sub">{c.sub}</div>
      <div className="pc-attrs">
        {c.attrs.map((a) => (
          <div key={a.code} className={`pc-attr ${a.value != null && a.value < 40 ? "low" : ""}`} title={a.label}>
            <span className="pc-code">{a.code}</span><span className="pc-val">{a.value ?? "—"}</span>
          </div>
        ))}
      </div>
      {size === "lg" && (
        <>
          {c.alt_positions.length > 0 && <div className="pc-alt">Also plays: {c.alt_positions.join(" · ")}</div>}
          {c.traits.length > 0 && <div className="pc-traits">{c.traits.map((t) => <span key={t}>{t}</span>)}</div>}
        </>
      )}
    </>
  );
  const cls = `pcard ${tierOf(c.ovr)} ${size} ${you ? "you" : ""}`;
  return onClick
    ? <button className={`${cls} hit`} onClick={onClick} aria-label={`${c.name} card, overall ${c.ovr}`}>{body}</button>
    : <div className={cls}>{body}</div>;
}

export function CardSection({ you, top, nearest, legend, note, onPick }: {
  you: PlayerCard; top: PlayerCard[]; nearest: PlayerCard[]; legend: Record<string, string>; note: string;
  onPick: (c: PlayerCard) => void;
}) {
  const [view, setView] = useState<"top" | "nearest">("top");
  const list = view === "top" ? top : nearest;
  return (
    <section className="tile">
      <div className="tile-head">
        <span className="tile-title">Player cards</span>
        <div className="tabs" role="tablist" aria-label="Compare with">
          <button role="tab" aria-selected={view === "top"} className={view === "top" ? "on" : ""} onClick={() => setView("top")}>Top-rated holders</button>
          <button role="tab" aria-selected={view === "nearest"} className={view === "nearest" ? "on" : ""} onClick={() => setView("nearest")}>Most similar to you</button>
        </div>
      </div>
      <div className="pc-layout">
        <div className="pc-me">
          <PCard c={you} size="lg" you />
          <dl className="pc-legend">
            {Object.entries(legend).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
          </dl>
        </div>
        <div className="pc-grid">
          {list.map((c, i) => <PCard key={`${view}${i}`} c={c} onClick={() => onPick(c)} />)}
        </div>
      </div>
      <p className="small muted" style={{ margin: "10px 0 0" }}>{note} Holders are shown by company and title only. Select a card to compare it with yours.</p>
    </section>
  );
}

export function CardCompare({ you, them }: { you: PlayerCard; them: PlayerCard }) {
  return (
    <>
      <span className="kick acc">Card comparison</span>
      <h2>{them.name} · {them.sub}</h2>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <PCard c={you} you /><PCard c={them} />
      </div>
      <h3>Attribute by attribute</h3>
      {you.attrs.map((a, i) => {
        const t = them.attrs[i]; const d = (a.value ?? 0) - (t.value ?? 0);
        return (
          <div key={a.code} className="fac" style={{ cursor: "inherit", gridTemplateColumns: "150px minmax(0,1fr) 60px" }}>
            <span>{a.label}</span>
            <span className="track">
              <span className="fill" style={{ width: `${a.value ?? 0}%` }} />
              <span className="tick" style={{ left: `${t.value ?? 0}%` }} />
            </span>
            <span className={`gapv ${d < -5 ? "bad" : d > 5 ? "good" : ""}`}>{d > 0 ? "+" : ""}{d}</span>
          </div>
        );
      })}
      <div className="small muted">Bar = you · tick = this holder · number = your lead (+) or deficit (−) in percentile points.</div>
      <dl className="kv" style={{ marginTop: 10 }}>
        <dt>Overall</dt><dd>You {you.ovr} · them {them.ovr}</dd>
        <dt>Scarce experience</dt><dd>You {you.scarce ?? "—"} · them {them.scarce ?? "—"}</dd>
        <dt>Their traits</dt><dd>{them.traits.join(", ") || "none found in their profile text"}</dd>
      </dl>
    </>
  );
}
