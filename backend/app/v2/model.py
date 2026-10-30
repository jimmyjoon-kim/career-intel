"""v2 scoring model: base score vs role holders, peer comparison, gap plan, opportunity scores.

Base score S = weighted mean of factor percentiles, percentiles taken within the reference
population (people who hold the target role, read with the same reader).
Weights  w = (m * expert + n * market) / (m + n), m = 50 (prior strength), n = reference size.
Position = percentile of S among the reference holders' own scores; 95% interval by bootstrap.
Gap on factor f = w_f * (P_holder_median - P_you). > +0.5 = gap, < -0.5 = lead (differentiator).
Opportunity score = same composite with weights re-emphasised by one posting's requirements.
No probabilities or hire likelihoods are produced anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .reader import LEVEL_NAMES, SCARCE_TAGS

# Bump on any change to factors, weights or rules; every stored score carries it.
MODEL_VERSION = "v3.0"

FACTORS = ["YOE", "CT", "LV", "FN", "DM", "UQ", "AC", "ED", "AI", "TK"]
FACTOR_LABELS = {"YOE": "Years of experience", "CT": "Company tier & journey", "AI": "Current AI relevance", "TK": "Technical depth", "LV": "Level held",
                 "FN": "Function evidence", "DM": "Domain evidence", "UQ": "Scarce experience", "AC": "Quantified outcomes", "ED": "Education (degree level)"}
W_EXPERT = {"YOE": 15, "CT": 20, "LV": 20, "FN": 15, "DM": 10, "UQ": 10, "AC": 5, "ED": 5, "AI": 10, "TK": 5}
# Market weights: discrimination of each factor between holders and non-target hires (title-based run, 2026-10-27).
W_MARKET = {"YOE": 0.1, "CT": 13.2, "LV": 22.7, "FN": 50.4, "DM": 4.3, "UQ": 2.3, "AC": 7.0}
PRIOR_M = 50
GOWER_RANGE = {"YOE": 30, "CT": 2, "LV": 5, "FN": 1, "DM": 1, "UQ": 2.5, "AC": 20, "ED": 2, "AI": 1, "TK": 1}
GAP_CLASS = {
    "YOE": ("structural", "Time at level; 12 months per year of gap."),
    "CT": ("structural", "Stepping stone: a role at a Tier 1/2 employer; counts once held 12+ months."),
    "LV": ("structural", "Band held 12+ months."),
    "FN": ("capability", "State partnership / alliance / channel scope in role descriptions; 0-6 months if the work exists."),
    "DM": ("capability", "Commercial work in the missing domain (AI, SaaS, ad tech, mobile)."),
    "UQ": ("capability", "Scarce experience: hyperscaler co-sell, GSI alliances, government, 0-to-1 builds."),
    "AC": ("capability", "Write quantified outcomes into role descriptions; 0-3 months."),
    "ED": ("capability", "Complete a graduate degree; counts from its completion date."),
    "AI": ("capability", "Commercial work on an AI product in the last 24 months, or an AI graduate degree."),
    "TK": ("capability", "Technical role, technical degree or technical product work (SDK/API, platform, ML)."),
}
TIME_TO_CLOSE = {"YOE": None, "CT": 24, "LV": 18, "FN": 3, "DM": 9, "UQ": 9, "AC": 2, "ED": 24, "AI": 6, "TK": 6}
TAG_LABELS = {
    "func_partnerships": "Partnerships / alliances", "func_bd": "Business development", "func_channel": "Channel / reseller / GSI",
    "domain_adtech": "Ad tech", "domain_ai": "AI", "domain_saas": "SaaS / cloud", "domain_mobile": "Mobile / gaming",
    "skill_hyperscaler": "Hyperscaler partnerships", "skill_govtech": "Government sector",
    "skill_consulting_firm_background": "Consulting-firm background", "skill_0to1_build": "0-to-1 build",
    "team_mgmt": "People management", "team_large": "Large team (20+)", "pnl_ownership": "P&L ownership",
    "func_sales_leadership": "Sales / commercial leadership",
}
# Posting requirement tags -> the factor they emphasise.
TAG_FACTOR = {
    **{t: "FN" for t in ["func_partnerships", "func_bd", "func_channel", "func_alliances_gsi", "func_ad_sales", "func_growth",
                         "func_rev_strategy", "func_sales_leadership", "func_growth_marketing", "func_product_strategy"]},
    **{t: "DM" for t in ["domain_adtech", "domain_ai", "domain_saas", "domain_mobile", "domain_marketplace", "domain_other"]},
    **{t: "UQ" for t in ["skill_hyperscaler", "skill_govtech", "skill_consulting_firm_background", "skill_0to1_build",
                         "skill_si_gsi", "skill_cosell"]},
    **{t: "LV" for t in ["team_mgmt", "team_large", "pnl_ownership", "skill_exec_presence", "mgmt_tenure_stated"]},
    **{t: "ED" for t in ["edu_bachelors"]},
    **{t: "AI" for t in ["skill_llm_ai_products"]},
    **{t: "TK" for t in ["edu_technical", "skill_sdk_api"]},
}
# Product level names -> reader bands
LEVEL_TO_BAND = {"IC": 0, "Manager": 0, "Senior Manager": 0, "Director": 1, "Head": 2, "Sr Director": 2, "VP": 3, "SVP": 4, "C-level": 5}


@dataclass
class Reference:
    cluster: str
    rows: list[dict]  # each: {"company","title", factor values..., "tags": {...}}

    @property
    def n(self) -> int:
        return len(self.rows)


def hybrid_weights(n: int, factors: list[str] | None = None) -> dict[str, float]:
    """Factors without a market estimate (ED: non-target hires' education not read) keep their expert share."""
    factors = factors or FACTORS
    te = sum(W_EXPERT[k] for k in factors)
    exp = {k: W_EXPERT[k] / te for k in factors}
    mk = {k: W_MARKET[k] for k in factors if k in W_MARKET}
    missing = sum(exp[k] for k in factors if k not in W_MARKET)
    tm = sum(mk.values())
    mkt = {k: (mk[k] / tm * (1 - missing) if k in mk else exp[k]) for k in factors}
    return {k: (PRIOR_M * 100 * exp[k] + n * 100 * mkt[k]) / (PRIOR_M + n) for k in factors}


def scarcity(ref_rows: list[dict]) -> dict[str, float]:
    n = len(ref_rows) or 1
    return {t: sum(1 for r in ref_rows if r["tags"].get(t, 0) > 0) / n for t in SCARCE_TAGS}


def with_uq(f: dict, prev: dict[str, float]) -> dict:
    f = dict(f)
    f["UQ"] = sum((1 - prev[t]) * f["tags"].get(t, 0) for t in SCARCE_TAGS)
    return f


def _vec(f: dict) -> np.ndarray:
    return np.array([np.nan if f.get(k) is None else float(f[k]) for k in FACTORS])


def pct_matrix(X: np.ndarray, ref: np.ndarray) -> np.ndarray:
    out = np.full(X.shape, np.nan)
    for j in range(X.shape[1]):
        rj = ref[:, j]
        rj = rj[~np.isnan(rj)]
        if not len(rj):
            continue
        xj = X[:, j]
        out[:, j] = np.where(np.isnan(xj), np.nan, 100 * ((xj[:, None] > rj[None, :]).sum(1)
                                                         + 0.5 * (xj[:, None] == rj[None, :]).sum(1)) / len(rj))
    return out


def composite(P: np.ndarray, wv: np.ndarray) -> np.ndarray:
    ok = ~np.isnan(P)
    num = np.nansum(np.where(ok, P, 0) * wv[None, :], axis=1)
    den = (ok * wv[None, :]).sum(1)
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def position(x: float, arr: np.ndarray) -> float:
    arr = arr[~np.isnan(arr)]
    return float(100 * (np.sum(arr < x) + 0.5 * np.sum(arr == x)) / len(arr)) if len(arr) else float("nan")


def _r(x, d=1):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), d)


def _gower(a: dict, b: dict) -> float:
    ds = n = 0
    for k in FACTORS:
        if a.get(k) is None or b.get(k) is None:
            continue
        ds += abs(a[k] - b[k]) / GOWER_RANGE[k]
        n += 1
    return ds / n if n else 1.0


def base_scorecard(user_f: dict, ref: Reference, *, months_left: int | None = None, n_boot: int = 1000, seed: int = 7) -> dict:
    prev = scarcity(ref.rows)
    rows = [with_uq(r, prev) for r in ref.rows]
    uf = with_uq(user_f, prev)
    M = np.array([_vec(r) for r in rows])
    U = _vec(uf)
    ed_cov = sum(1 for r in rows if r.get("ED") is not None) / len(rows)
    w = hybrid_weights(ref.n)
    if ed_cov < 0.5:  # education enters the score only when at least half the holders' education is known
        w["ED"] = 0.0
    wv = np.array([w[k] for k in FACTORS])
    P_h, P_u = pct_matrix(M, M), pct_matrix(U[None, :], M)[0]
    S_h, S_u = composite(P_h, wv), float(composite(P_u[None, :], wv)[0])
    pos = position(S_u, S_h)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        R = M[rng.integers(0, len(M), len(M))]
        boots.append(position(float(composite(pct_matrix(U[None, :], R), wv)[0]), composite(pct_matrix(R, R), wv)))
    sc = S_h[~np.isnan(S_h)]
    hist, edges = np.histogram(sc, bins=list(range(0, 101, 10)))

    factors = []
    for j, k in enumerate(FACTORS):
        hp = P_h[:, j]
        hp = hp[~np.isnan(hp)]
        hv = [r[k] for r in rows if r.get(k) is not None]
        up = None if np.isnan(P_u[j]) else float(P_u[j])
        med_p = float(np.median(hp)) if len(hp) else None
        delta = (w[k] / 100 * (med_p - up)) if (up is not None and med_p is not None) else None
        factors.append({"factor": k, "label": FACTOR_LABELS[k], "weight": _r(w[k]), "you_value": _r(uf.get(k), 2),
                        "you_pct": _r(up), "holder_median_value": _r(np.median(hv), 2) if hv else None,
                        "holder_median_pct": _r(med_p), "share_above_you": _r(np.mean(hp > up), 2) if up is not None else None,
                        "delta": _r(delta), "coverage": _r(len(hv) / len(rows), 2)})

    gaps, leads = [], []
    for f in sorted(factors, key=lambda f: -(f["delta"] or 0)):
        if f["delta"] is None:
            continue
        k = f["factor"]
        if f["delta"] > 0.5:
            cls, action = GAP_CLASS[k]
            ttc = (round(12 * max(0.0, (f["holder_median_value"] or 0) - (uf["YOE"] or 0))) if k == "YOE" else TIME_TO_CLOSE[k])
            gaps.append({**f, "class": cls, "action": action, "months_to_close": ttc,
                         "closable_by_target": (ttc <= months_left) if (months_left is not None and ttc is not None) else None})
        elif f["delta"] < -0.5:
            leads.append({**f, "class": "differentiator"})

    # Tag-level focus areas: common among holders, weaker or older in your record.
    prevalence = {t: sum(1 for r in rows if r["tags"].get(t, 0) > 0) / len(rows) for t in TAG_LABELS}
    focus = []
    for t, p in sorted(prevalence.items(), key=lambda x: -x[1]):
        yours = uf["tags"].get(t, 0)
        if yours < 1 and (p >= 0.3 or t in SCARCE_TAGS):
            focus.append({"tag": t, "label": TAG_LABELS[t], "holder_share": round(p, 2), "your_weight": yours,
                          "status": "older than 8 years (counts half)" if yours == 0.5 else "not found in your text",
                          "note": "rule over-matches; re-measure" if t == "skill_consulting_firm_background" and p > 0.3 else ""})

    # Tag-level differentiators: evidenced (recent) in your text and held by under 30% of holders. Not part of the score.
    rare = [{"tag": t, "label": TAG_LABELS[t], "holder_share": round(p, 2)}
            for t, p in sorted(prevalence.items(), key=lambda x: x[1]) if uf["tags"].get(t, 0) >= 1 and p < 0.3]

    order = sorted(range(len(rows)), key=lambda i: _gower(uf, rows[i]))
    peers = []
    for i in order[:8]:
        comp = {k: _r(w[k] / 100 * (P_h[i][j] - P_u[j])) for j, k in enumerate(FACTORS)
                if not (np.isnan(P_h[i][j]) or np.isnan(P_u[j]))}
        peers.append({"company": rows[i]["company"], "title": rows[i]["title"], "score": _r(S_h[i]),
                      "similarity": round(1 - _gower(uf, rows[i]), 3),
                      "ahead_on": [FACTOR_LABELS[k] for k, v in sorted(comp.items(), key=lambda x: -x[1]) if v > 0.5][:3],
                      "you_lead_on": [FACTOR_LABELS[k] for k, v in sorted(comp.items(), key=lambda x: x[1]) if v < -0.5][:3],
                      "components": {FACTOR_LABELS[k]: v for k, v in comp.items()},
                      "values": {k: _r(rows[i].get(k), 2) for k in FACTORS}})

    return {
        "cluster": ref.cluster, "n_reference": ref.n, "weights": {k: _r(v) for k, v in w.items()},
        "base_score": _r(S_u), "position": _r(pos),
        "position_ci95": [_r(np.percentile(boots, 2.5)), _r(np.percentile(boots, 97.5))] if boots else [None, None],
        "holders": {"scores": sorted(_r(x) for x in sc),
                    "tier_share": {f"Tier {t}": round(sum(1 for r in rows if r.get("tier") == t) / len(rows), 2) for t in (1, 2, 3)},
                    "median": _r(np.median(sc)), "p25": _r(np.percentile(sc, 25)), "p75": _r(np.percentile(sc, 75)),
                    "hist": {"edges": [int(e) for e in edges], "counts": [int(c) for c in hist]}},
        "factors": factors, "gaps": gaps, "differentiators": leads, "focus_areas": focus, "rare_strengths": rare,
        "prevalence": {t: round(p, 2) for t, p in prevalence.items()}, "tag_labels": TAG_LABELS, "peers": peers,
        "scarcity_prevalence": {t: round(p, 2) for t, p in prev.items()},
        "benchmark": _benchmark(S_u, S_h, P_h, P_u, w, rows, uf, M, wv, prev),
        "cards": _cards(S_u, S_h, P_h, P_u, rows, uf, order),
        "_internal": {"P_u": P_u, "M": M, "wv": wv, "user": uf},
    }


def opportunity(card: dict, posting_tags: list[str], tag_weights: dict[str, int], *, posting_level: str = "",
                years_required: int | None = None) -> dict:
    """Re-weight the base composite by one posting's requirements.

    Emphasis d_f = share of the posting's requirement weight that maps to factor f
    (discrimination weight 0/1/3 from the posting's cluster; common-minimum tags count 1).
    w'_f = w_f * (1 + d_f). Thresholds (years, level) are reported as hard gaps, not scored.
    """
    internal = card["_internal"]
    w = dict(zip(FACTORS, internal["wv"]))
    emph = {k: 0.0 for k in FACTORS}
    for t in posting_tags:
        f = TAG_FACTOR.get(t)
        if f:
            emph[f] += max(1, tag_weights.get(t, 3))
    total = sum(emph.values())
    d = {k: (v / total if total else 0.0) for k, v in emph.items()}
    w2 = {k: w[k] * (1 + d[k]) for k in FACTORS}
    s = sum(w2.values())
    w2 = {k: 100 * v / s for k, v in w2.items()}
    wv2 = np.array([w2[k] for k in FACTORS])
    M, P_u = internal["M"], internal["P_u"]
    S_u = float(composite(P_u[None, :], wv2)[0])
    pos = position(S_u, composite(pct_matrix(M, M), wv2))
    uf = internal["user"]
    thresholds = []
    if years_required and uf.get("YOE_raw") is not None and uf["YOE_raw"] < years_required:
        thresholds.append(f"{years_required}+ years required; your counted years: {uf['YOE_raw']}")
    need = LEVEL_TO_BAND.get(posting_level)
    have = uf.get("LV_max")
    if need is not None and have is not None and have < need:
        thresholds.append(f"Level {posting_level} required; highest band held 12+ months: {LEVEL_NAMES[have]}")
    shifts = sorted(((k, w2[k] - card["weights"][k]) for k in FACTORS), key=lambda x: -x[1])
    return {"score": _r(S_u), "position": _r(pos), "delta_vs_base": _r(S_u - card["base_score"]),
            "weights": {k: _r(v) for k, v in w2.items()},
            "emphasised": [FACTOR_LABELS[k] for k, v in shifts if v > 0.5][:3],
            "thresholds": thresholds}


CARD_ATTRS = [("LVL", "LV", "Level held"), ("FUN", "FN", "Function evidence"), ("DOM", "DM", "Domain breadth"),
              ("EXP", "YOE", "Years of experience"), ("IMP", "AC", "Quantified impact"), ("TIER", "CT", "Employer tier"),
              ("EDU", "ED", "Education (degree level)"), ("SCA", "UQ", "Scarce experience"),
              ("AI", "AI", "Current AI relevance"), ("TEC", "TK", "Technical depth")]
TRAIT_TAGS = ["team_large", "pnl_ownership", "func_sales_leadership", "skill_0to1_build", "skill_hyperscaler",
              "skill_govtech", "skill_consulting_firm_background", "func_channel"]
_POS = [(r"general manager|\bgm\b|managing director|country manager", "GM"), (r"\bceo\b|\bcro\b|chief", "CXO"),
        (r"alliance", "ALL"), (r"partner", "PTN"), (r"business development|\bbd\b", "BD"), (r"growth", "GRW"),
        (r"monetiz|ads?\b|advertis", "ADS"), (r"sales|revenue|commercial", "SAL")]


def position_code(title: str) -> str:
    import re as _re
    for pat, code in _POS:
        if _re.search(pat, (title or "").lower()):
            return code
    return "PTN"


def _rating(p) -> int | None:
    return None if p is None or (isinstance(p, float) and np.isnan(p)) else int(max(1, min(99, round(float(p)))))


def _card(score, pcts, tags) -> dict:
    return {"ovr": _rating(score),
            "attrs": [{"code": c, "label": l, "value": _rating(pcts[FACTORS.index(k)])} for c, k, l in CARD_ATTRS],
            "scarce": _rating(pcts[FACTORS.index("UQ")]),
            "traits": [TAG_LABELS[t] for t in TRAIT_TAGS if (tags or {}).get(t, 0) >= 1]}


def _cards(S_u, S_h, P_h, P_u, rows, uf, order) -> dict:
    """Player-card view: overall = base score; each attribute = percentile among role holders (1–99)."""
    you = _card(S_u, P_u, uf["tags"])
    rr = uf.get("recent_role") or {}
    # Primary position: the role family you held longest in the last 10 years; alternates from your other roles.
    months: dict[str, int] = {}
    for r in uf.get("roles", []):
        if r.get("counted") and r.get("recency_weight", 1) == 1.0:
            code = position_code(r["title"])
            months[code] = months.get(code, 0) + r["months"]
    ranked = sorted(months, key=lambda c: -months[c])
    for t, code in (("func_partnerships", "PTN"), ("func_bd", "BD"), ("func_sales_leadership", "SAL"), ("func_channel", "CHN")):
        if uf["tags"].get(t, 0) >= 1 and code not in ranked:
            ranked.append(code)
    you.update({"name": "You", "position": ranked[0] if ranked else position_code(rr.get("title", "")),
                "alt_positions": ranked[1:5], "sub": f'{rr.get("title", "")} · {rr.get("company", "")}'.strip(" ·")})
    def holder(i):
        c = _card(S_h[i], P_h[i], rows[i]["tags"])
        c.update({"name": rows[i]["company"], "sub": rows[i]["title"], "position": position_code(rows[i]["title"]),
                  "alt_positions": [], "index": int(i)})
        return c
    top = sorted(range(len(rows)), key=lambda i: -(S_h[i] if not np.isnan(S_h[i]) else -1))[:8]
    return {"you": you, "top": [holder(i) for i in top], "nearest": [holder(i) for i in order[:8]],
            "legend": {c: l for c, _, l in CARD_ATTRS},
            "note": "Overall = base score. Each attribute = your percentile among role holders (1–99), so 50 is the median holder."}


def _score_with(uf: dict, M: np.ndarray, wv: np.ndarray, prev: dict) -> tuple[float, float]:
    f = with_uq(uf, prev)
    P = pct_matrix(_vec(f)[None, :], M)
    s = float(composite(P, wv)[0])
    return s, position(s, composite(pct_matrix(M, M), wv))


def _benchmark(S_u, S_h, P_h, P_u, w, rows, uf, M, wv, prev) -> dict:
    """What a score means, who scores above you and why, and what would move your score."""
    sc = S_h[~np.isnan(S_h)]
    above = [i for i in range(len(rows)) if not np.isnan(S_h[i]) and S_h[i] > S_u]
    drivers = {}
    for j, k in enumerate(FACTORS):
        vals = [w[k] / 100 * (P_h[i][j] - P_u[j]) for i in above if not (np.isnan(P_h[i][j]) or np.isnan(P_u[j]))]
        drivers[k] = {"label": FACTOR_LABELS[k], "avg_points": _r(np.mean(vals)) if vals else None,
                      "holders_ahead": sum(1 for v in vals if v > 0.5)}
    tiers = {t: sum(1 for i in above if rows[i].get("tier") == t) for t in (1, 2, 3)}
    # What-ifs: one change at a time, everything else as read.
    whatifs = []
    cases = [
        ("Recent employer at Tier 2 (e.g. 12+ months at a $10B+ company)", "CT", {"CT": 2, "tier": 2}),
        ("Recent employer at Tier 1 (top-10 tech)", "CT", {"CT": 3, "tier": 1}),
        ("Partnerships, BD and channel all evidenced in the last 8 years", "FN",
         {"tags": {**uf["tags"], "func_partnerships": 1.0, "func_bd": 1.0, "func_channel": 1.0}, "FN": 1.0}),
        ("Hyperscaler partnership experience added", "UQ", {"tags": {**uf["tags"], "skill_hyperscaler": 1.0}}),
        ("Two more quantified outcomes written into roles", "AC", {"AC": (uf.get("AC") or 0) + 2}),
    ]
    if uf.get("ED_target") is not None and (uf.get("ED") is None or uf["ED_target"] > uf["ED"]):
        change = {"ED": uf["ED_target"]}
        if uf.get("AI_target") is not None:
            change["AI"] = uf["AI_target"]
        cases.insert(0, (f"Degrees in progress completed by your target date ({uf.get('target_date') or 'target'})", "ED", change))
    for label, k, change in cases:
        alt = {**uf, **change}
        if alt == uf or (k == "FN" and (uf.get("FN") or 0) >= 1) or (k == "CT" and (uf.get("CT") or 0) >= change.get("CT", 0)):
            continue
        s, p = _score_with(alt, M, wv, prev)
        whatifs.append({"change": label, "factor": FACTOR_LABELS[k], "score": _r(s), "delta": _r(s - S_u), "position": _r(p),
                        "closable": GAP_CLASS[k][0] == "capability", "scheduled": k == "ED"})
    whatifs.sort(key=lambda x: -(x["delta"] or 0))
    return {
        "max": _r(sc.max()), "p90": _r(np.percentile(sc, 90)), "p75": _r(np.percentile(sc, 75)),
        "median": _r(np.median(sc)), "p25": _r(np.percentile(sc, 25)), "min": _r(sc.min()),
        "ceiling_note": "A score of 100 would mean ranking first among holders on every factor; no holder does. "
                        "The highest holder scores " + str(_r(sc.max())) + ".",
        "n_above": len(above), "above_tiers": {f"Tier {t}": n for t, n in tiers.items()},
        "drivers": sorted(drivers.values(), key=lambda d: -(d["avg_points"] or 0)),
        "whatifs": whatifs,
    }


def public(card: dict) -> dict:
    return {k: v for k, v in card.items() if not k.startswith("_")}
