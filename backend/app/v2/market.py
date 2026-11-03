"""Market fit: experience in the market a job is based in, and multi-region scope (v3.7, 2026-11-03).

Research basis (docs/model.md, "Market fit"): employers discount experience gained outside the host market on average
(Oreopoulos field experiment: +5.1 points callback from a 5.9% base when local experience is added; smaller gap at
large employers), returns to foreign experience are higher from high-income countries (NBER w21914), and the gap
shrinks over time. No source gives a size for Director/VP commercial roles, so the parameters below are judgments,
stated as such, to be re-estimated from outcomes (applications, interviews, offers).

Job market t of a posting: the region in its title ("Head of APAC") or, otherwise, of its location; "global" when the
title says global / worldwide / international. Effective months in t:
    E_t = M_in + 0.5 * M_scope + 0.25 * M_hq          (capped at 60)
    M_in    months in roles located in t (a different country in the same region counts half, for APAC / EMEA)
    M_scope months in roles located elsewhere whose text states responsibility for t (or global scope)
    M_hq    months at an employer headquartered in t, without t scope
Job fit, for a posting based in t (not global):
    without a local-market requirement: fit x (1 - P * (1 - min(E_t, 36) / 36)), P = 0.15 (0.075 for multi-region roles)
    with a stated US-market requirement (geo_us_market): that requirement is scored with credit min(E_t / 24, 1) instead
    multi-region roles (geo_multi_region or global title): + 5 * min(R / 36, 1) points, R = months in multi-region roles
Work authorization stays a separate pass/fail screen; it never enters E_t or P."""

from __future__ import annotations

import re

from .geo import APAC_LOC, EMEA_LOC, MULTI, US_LOC, US_WORK
from .geo import regions as _geo_regions

LATAM_LOC = re.compile(r"\blatam\b|latin america|brazil|s[ãa]o paulo|mexico|ciudad de m[ée]xico|buenos aires|argentina|"
                       r"bogot[áa]|colombia|chile|santiago|peru|lima\b", re.I)


US_STATES = re.compile(r"\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|"
                       r"idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|"
                       r"minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|"
                       r"new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|"
                       r"south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|"
                       r"wisconsin|wyoming)\b", re.I)


def regions(loc: str) -> set[str]:
    out = _geo_regions(loc or "")
    if not out and US_STATES.search(loc or ""):
        out.add("US")
    if LATAM_LOC.search(re.sub(r"new mexico", "", loc or "", flags=re.I)):
        out.add("LATAM")
    return out

P_DEFAULT = 0.15     # judgment: largest share of fit removed with no experience in the job's market
RAMP = 36            # judgment: months of effective experience at which the reduction is gone
REQ_FULL = 24        # judgment: months for full credit on a stated local-market requirement
MULTI_BONUS = 0.05   # judgment: up to 5 points for multi-region scope when the role is multi-region
MULTI_RAMP = 36

GLOBAL_TITLE = re.compile(r"\b(global|worldwide|international|intl)\b", re.I)
REGION_TITLE = [("APAC", re.compile(r"\bapac\b|asia[- ]pacific|\basia\b|\bjapac\b|\banz\b|southeast asia|\bsea\b", re.I)),
                ("EMEA", re.compile(r"\bemea\b|\beurope\b|\bmiddle east\b", re.I)),
                ("LATAM", re.compile(r"\blatam\b|latin america", re.I)),
                ("US", re.compile(r"north america|\bamericas\b|\bus&c\b|\bucan\b", re.I))]
COUNTRY = [("Korea", r"korea|seoul"), ("Japan", r"japan|tokyo"), ("Singapore", r"singapore"), ("China", r"china|beijing|shanghai|shenzhen"),
           ("Hong Kong", r"hong kong"), ("Taiwan", r"taiwan|taipei"), ("India", r"india|bangalore|bengaluru|mumbai|delhi|gurgaon"),
           ("Australia", r"australia|sydney|melbourne"), ("UK", r"united kingdom|\buk\b|london"), ("Germany", r"germany|berlin|munich"),
           ("France", r"france|paris"), ("Israel", r"israel|tel aviv"), ("Netherlands", r"netherlands|amsterdam"),
           ("Ireland", r"ireland|dublin"), ("UAE", r"dubai|uae|abu dhabi")]
SCOPE = {"US": US_WORK, "APAC": re.compile(r"[^.;]{0,60}(?:" + APAC_LOC.pattern + r")[^.;]{0,60}", re.I),
         "EMEA": re.compile(r"[^.;]{0,60}(?:" + EMEA_LOC.pattern + r")[^.;]{0,60}", re.I),
         "LATAM": re.compile(r"[^.;]{0,60}(?:" + LATAM_LOC.pattern + r")[^.;]{0,60}", re.I)}
GLOBAL_SCOPE = re.compile(r"\bglobal (?:accounts|business|partnerships|revenue|sales|go-to-market|clients|partners)\b|"
                          r"\bworldwide\b", re.I)


def country(loc: str) -> str | None:
    for name, pat in COUNTRY:
        if re.search(pat, loc or "", re.I):
            return name
    return "US" if US_LOC.search(loc or "") else None


def posting_market(title: str, location: str, multi_tag: bool = False) -> dict:
    t = title or ""
    if GLOBAL_TITLE.search(t):
        return {"market": "global", "country": None, "multi": True, "basis": f"title: {t[:80]}"}
    for reg, rx in REGION_TITLE:
        if rx.search(t):
            return {"market": reg, "country": None, "multi": multi_tag or reg != "US", "basis": f"title: {t[:80]}"}
    reg = regions(location or "")
    if len(reg) == 1:
        return {"market": next(iter(reg)), "country": country(location), "multi": multi_tag, "basis": f"location: {location[:80]}"}
    if re.search(r"remote", location or "", re.I) and not reg:
        return {"market": None, "country": None, "multi": multi_tag, "basis": "remote, no region stated"}
    return {"market": None, "country": None, "multi": multi_tag, "basis": "location not read"}


def _hq_region(company: str) -> str | None:
    import json
    from pathlib import Path

    global _HQ
    if _HQ is None:
        _HQ = {}
        for name in ("sector_adtech.json", "sector_ai.json"):
            f = Path(__file__).resolve().parents[2] / "seed" / name
            if not f.exists():
                f = Path("/app/seed") / name
            if f.exists():
                for c in json.loads(f.read_text()).get("companies", []):
                    reg = regions(c.get("hq") or "")
                    if len(reg) == 1:
                        for n in [c["name"]] + list(c.get("aliases") or []):
                            if len(n) >= 3:
                                _HQ[n.lower()] = next(iter(reg))
    base = re.sub(r"\s*\(.*?\)\s*", " ", company or "").strip().lower()
    for n, reg in _HQ.items():
        if re.search(r"\b" + re.escape(n) + r"\b", base):
            return reg
    return None


_HQ: dict | None = None


def effective_months(roles: list[dict], market: str | None, ctry: str | None = None) -> dict:
    """E_t with its parts and the evidence lines. Roles: title, company, location, months, desc."""
    if market in (None, "global"):
        return {"E": None, "in": 0, "scope": 0, "hq": 0, "evidence": []}
    m_in = m_scope = m_hq = 0.0
    ev = []
    for r in roles:
        n = int(r.get("months") or 0)
        loc = r.get("location") or ""
        reg = regions(loc)
        label = f'{r.get("title", "")} @ {r.get("company", "")}'
        text = " ".join([r.get("title", "")] + list(r.get("desc") or []))
        if market in reg and len(reg) > 1:  # several regions in one location line: covered, not based there
            m_scope += n
            ev.append(f"{label}: location lists several regions ({loc[:60]}); counted as covering {market}")
            continue
        if market in reg:
            same = 1.0
            if market != "US" and ctry and country(loc) and country(loc) != ctry:
                same = 0.5
            m_in += same * n
            ev.append(f"{label}: located {loc}" + (" (same region, other country: half)" if same < 1 else ""))
            continue
        sm = SCOPE[market].search(text) or GLOBAL_SCOPE.search(text)
        if sm:
            m_scope += n
            ev.append(f'{label}: "{sm.group(0).strip()[:120]}"')
            continue
        if _hq_region(r.get("company", "")) == market:
            m_hq += n
            ev.append(f"{label}: employer headquartered in {market}")
    E = min(60.0, m_in + 0.5 * m_scope + 0.25 * m_hq)
    return {"E": round(E, 1), "in": round(m_in), "scope": round(m_scope), "hq": round(m_hq), "evidence": ev[:6]}


def multi_months(roles: list[dict]) -> int:
    out = 0
    for r in roles:
        text = " ".join([r.get("title", "")] + list(r.get("desc") or []))
        if len(regions(r.get("location") or "")) > 1 or MULTI.search(text) or GLOBAL_SCOPE.search(text):
            out += int(r.get("months") or 0)
    return out


def adjust(rank_score: float, pm: dict, eff: dict, has_us_req: bool, R: int) -> tuple[float, dict]:
    """Fit after market fit. Returns (new score 0-1, explanation)."""
    t, E = pm["market"], eff.get("E")
    out = {"market": t, "basis": pm["basis"], "effective_months": E, "parts": {k: eff.get(k) for k in ("in", "scope", "hq")},
           "evidence": eff.get("evidence", []), "multi_region": pm["multi"], "multi_months": R, "change": 0.0}
    s = rank_score
    if t not in (None, "global") and E is not None and not (has_us_req and t == "US"):
        p = P_DEFAULT / 2 if pm["multi"] else P_DEFAULT
        factor = 1 - p * (1 - min(E, RAMP) / RAMP)
        s *= factor
        out["reduction_pct"] = round(100 * (1 - factor), 1)
    if pm["multi"] and R > 0:
        s = min(1.0, s + MULTI_BONUS * min(R / MULTI_RAMP, 1))
        out["multi_bonus"] = round(100 * MULTI_BONUS * min(R / MULTI_RAMP, 1), 1)
    out["change"] = round(100 * (s - rank_score), 1)
    return s, out


def target_market(locations: list[str] | None) -> str | None:
    """The market of your first target location (US / APAC / EMEA), used for the peer score's market factor."""
    for loc in locations or []:
        reg = regions(loc)
        if len(reg) == 1:
            return next(iter(reg))
    return None
