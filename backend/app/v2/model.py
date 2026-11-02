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
MODEL_VERSION = "v3.5"

FACTORS = ["YOE", "CT", "LV", "FN", "DM", "UQ", "AC", "ED", "AI", "TK", "PD", "SCH", "FLD", "US", "FT", "SG"]
# Factors read from new peer files only: they count once this many holders in the comparison group have a value.
NEW_FACTORS = {"PD": 20, "SCH": 20, "FLD": 20, "US": 20, "FT": 20, "SG": 20}
FACTOR_LABELS = {"YOE": "Years of experience", "CT": "Company tier & journey", "AI": "Current AI relevance", "TK": "Technical depth", "LV": "Level held",
                 "FN": "Function evidence", "DM": "Domain fit to the role", "UQ": "Scarce experience", "AC": "Quantified outcomes", "ED": "Education (degree level)",
                 "PD": "Hired into major companies", "SCH": "School tier", "FLD": "Degree field",
                 "US": "US market experience", "FT": "Same function at a major company",
                 "SG": "Ad tech sides covered (demand, supply, unified)"}
# Expert prior, set from published evidence (docs/model.md): type of experience (function, domain, same function at a
# major company) and level lead; tenure counts up to a floor; US experience counts; school and degree matter little at
# senior level (the school effect fades with experience). Blended with market weights as outcome data accrue.
W_EXPERT = {"YOE": 10, "CT": 5, "LV": 15, "FN": 16, "DM": 9, "UQ": 3, "AC": 2, "ED": 3, "AI": 6, "TK": 3,
            "PD": 5, "SCH": 2, "FLD": 2, "US": 12, "FT": 14, "SG": 0}  # SG weighted for ad families only (below)
# Market weights: discrimination of each factor between holders and non-target hires (title-based run, 2026-10-27).
W_MARKET = {"YOE": 0.1, "CT": 13.2, "LV": 22.7, "FN": 50.4, "DM": 4.3, "UQ": 2.3, "AC": 7.0}
PRIOR_M = 50
GOWER_RANGE = {"YOE": 30, "CT": 2, "LV": 5, "FN": 1, "DM": 1, "UQ": 2.5, "AC": 20, "ED": 2, "AI": 1, "TK": 1, "PD": 4, "SCH": 2, "FLD": 1,
               "US": 60, "FT": 2, "SG": 2}
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
    "PD": ("structural", "A role of 12+ months at a Tier 1 or Tier 2 employer; each distinct employer counts once."),
    "SCH": ("structural", "School tier of a completed degree (QS top 30 / 31-100); a new degree counts from completion."),
    "FLD": ("structural", "Field of a completed degree."),
    "US": ("structural", "Months in US-based roles (counted up to 60); accrues after a move to a US role."),
    "FT": ("structural", "A role of 12+ months in this function at a Tier 1 (2 points) or Tier 2 (1 point) employer."),
    "SG": ("capability", "Demand-side (advertisers, agencies) and supply-side (publishers, monetization) work in the last 10 years; both = unified."),
}
TIME_TO_CLOSE = {"YOE": None, "CT": 24, "LV": 18, "FN": 3, "DM": 9, "UQ": 9, "AC": 2, "ED": 24, "AI": 6, "TK": 6,
                 "PD": 24, "SCH": None, "FLD": None, "US": 12, "FT": 24, "SG": 12}
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


# Function evidence that counts for each role family (tags stored for every holder). Growth's own signal is read only
# for holders collected from Oct 31, 2026 on; it counts once 20 holders in the group have it.
FAMILY_FN = {
    "partnerships": ["func_partnerships", "func_bd", "func_channel"],
    "bd / alliances": ["func_bd", "func_partnerships"],
    "ad sales": ["func_ad_sales", "func_brand_agency_sales", "func_sales_leadership"],
    "gm / regional lead": ["pnl_ownership", "team_mgmt", "team_large"],
    "growth": ["func_growth"],
    "enterprise / tech sales": ["func_enterprise_sales", "func_sales_leadership"],
}


def family_view(f: dict, cluster: str, usable: list[str] | None = None, seen_tags: set | None = None) -> dict:
    """Function evidence for this family; major-company hires with Tier 1 employers counted double."""
    f = dict(f)
    tags = f.get("tags") or {}
    keys = usable if usable is not None else FAMILY_FN.get(cluster.split(" · ")[0].lower(), FAMILY_FN["partnerships"])
    f["FN"] = (sum(float(tags.get(t, 0)) for t in keys) / len(keys)) if keys else None
    if f.get("CT_tier_only") is not None:  # employer tier only: the IPO/acquisition bonus is dropped (counted elsewhere)
        f["CT"] = f["CT_tier_only"]
    if f.get("PD") is not None:
        f["PD"] = float(f["PD"]) + float(f.get("PD_t1") or 0)
    if f.get("geo_us_months") is not None:
        f["US"] = min(60.0, float(f["geo_us_months"]))
    if f.get("roles_anon") is not None:  # same function at a major company, from the anonymized role list
        fam = cluster.split(" · ")[0].lower()
        fam_tags = set(FAMILY_FN.get(fam, FAMILY_FN["partnerships"])) & set(seen_tags if seen_tags is not None else FAMILY_FN.get(fam, []))
        gm = fam == "gm / regional lead"  # general management: a VP/GM-band role, not a keyword
        best = 0
        for r in f["roles_anon"]:
            same = (r.get("lv") or 0) >= 3 if gm else bool(fam_tags & set(r.get("tags") or []))
            if r.get("months", 0) >= 12 and r.get("tier") in (1, 2) and same:
                best = max(best, 2 if r["tier"] == 1 else 1)
        f["FT"] = float(best) if (gm or fam_tags) else None
        # ad tech sides covered in the last 10 years of roles (before hire for holders)
        y1 = max((r.get("y1") or 0 for r in f["roles_anon"]), default=0)
        tags = [set(r.get("tags") or []) for r in f["roles_anon"] if (r.get("y1") or 0) >= y1 - 10]
        # only roles read with the demand-side tag (tag version 2); older reads stay unmeasured, same for everyone
        if f["roles_anon"] and all((r.get("tv") or 1) >= 2 for r in f["roles_anon"]):
            from .segment import sides_from_tags

            ugm = any(r.get("ugm") for r in f["roles_anon"] if (r.get("y1") or 0) >= y1 - 10)
            f["SG"] = sides_from_tags(tags, unified_gm=ugm)["SG"]
    return f


GATE_FACTORS = ["US", "FT", "FN", "DM"]
AD_FAMILIES = {"ad sales", "partnerships", "bd / alliances", "gm / regional lead"}
GATE_SHARE = 0.6

# Effective level: the title band adjusted by the size of the employer where it was held, so titles compare across
# company sizes (a Director at a 5,000+ company carries more scope than the same title at a 30-person startup, and a
# C-level title at a 5-person startup is not a public-company C-level). Same rule for you and every holder.
# Sources and limits: docs/model.md. Holders read before company sizes were recorded fall back to employer tier.
# Large companies (5,000+ employees, Tier 1/2) are the reference scale (no adjustment). Smaller employers: the title is
# read down by band, more for senior titles (bands: 0 Manager/IC, 1 Director, 2 Head/Sr Director, 3 VP/GM, 4 SVP/MD,
# 5 C-level). Basis (docs/model.md): about half of Directors at companies under ~500-1,000 people do not manage managers;
# executive orgs at companies under 100 people span ~15-50 people, close to a large-company Director's ~36 (Pave);
# startup-to-big-tech moves are typically 1-2 levels down (anecdotal). The exact steps are a judgment, capped at -3.
SIZE_STEPS = {  # size band -> {title band: adjustment}
    "large": {},
    "mid": {3: -1, 4: -1, 5: -1},                       # 500-4,999
    "small": {1: -1, 2: -1, 3: -2, 4: -2, 5: -2},       # 50-499
    "tiny": {1: -1, 2: -1, 3: -2, 4: -3, 5: -3},        # under 50: C-level reads as Head / Sr Director
}
SIZE_MAX_BAND = {"tiny": 1, "small": 2}  # under 50 people: at most Director; 50-499: at most Head / Sr Director
TIER_FALLBACK = {1: "large", 2: "large", 3: "small"}  # size not recorded (older reads): use employer tier


def effective_level(f: dict) -> dict:
    f = dict(f)
    if f.get("LV") is None:
        return f
    size = f.get("LV_size") if f.get("LV_size") in SIZE_STEPS else TIER_FALLBACK.get(f.get("tier"), "large")
    adj = SIZE_STEPS[size].get(int(f["LV"]), 0)
    f["LV_title"], f["LV_adj"], f["LV_size_used"] = f["LV"], adj, size
    f["LV"] = max(0, min(SIZE_MAX_BAND.get(size, 5), f["LV"] + adj))
    # A short last stint at a very small company does not erase the level held just before it: take the highest
    # size-adjusted level among roles of 12+ months that ended in the 3 years before the latest role ended.
    ra = [r for r in (f.get("roles_anon") or []) if r.get("lv") is not None and r.get("y1") and r.get("size")]
    if ra:
        last = max(r["y1"] for r in ra)
        best = max((_eff(r["lv"], r["size"], r.get("tier")) for r in ra
                    if (r.get("months") or 0) >= 12 and r["y1"] >= last - 3), default=None)
        if best is not None and best > f["LV"]:
            f["LV_from_earlier"] = True
            f["LV"] = best
    return f


def _eff(lv: int, size: str, tier) -> int:
    size = size if size in SIZE_STEPS else TIER_FALLBACK.get(tier, "large")
    return max(0, min(SIZE_MAX_BAND.get(size, 5), int(lv) + SIZE_STEPS[size].get(int(lv), 0)))


size_scaled = effective_level  # former name


def domain_fit(f: dict, dom_w: dict[str, float]) -> dict:
    f = dict(f)
    tot = sum(dom_w.values())
    if tot > 0 and f.get("tags") is not None:
        f["DM_breadth"] = f.get("DM")
        f["DM"] = sum(w * float(f["tags"].get(t, 0)) for t, w in dom_w.items()) / tot
    return f


# Factors where more stops helping: credit is capped at what the strongest quarter of holders have (75th percentile).
# Without the cap, a long, broad career outscores every holder by being "more" on each factor, while real holders are
# strong on a few things; the score would reward breadth and tenure rather than fit.
SATURATE = ["YOE", "LV", "DM", "AC", "UQ", "FN", "TK", "AI"]
CAP_Q = 75


def saturate(rows: list[dict], uf: dict, q: float | None = CAP_Q) -> tuple[list[dict], dict, dict]:
    if not q:
        return rows, uf, {}
    caps = {}
    for k in SATURATE:
        vals = [float(r[k]) for r in rows if r.get(k) is not None]
        if len(vals) >= 10:
            caps[k] = float(np.percentile(vals, q))
    def cap(f):
        f = dict(f)
        for k, c in caps.items():
            if f.get(k) is not None and float(f[k]) > c:
                f[k + "_uncapped"], f[k] = f[k], c
        return f
    return [cap(r) for r in rows], cap(uf), caps


def base_scorecard(user_f: dict, ref: Reference, *, months_left: int | None = None, n_boot: int = 1000, seed: int = 7,
                   cap_q: float | None = CAP_Q) -> dict:
    prev = scarcity(ref.rows)
    fam = ref.cluster.split(" · ")[0].lower()
    wanted = FAMILY_FN.get(fam, FAMILY_FN["partnerships"])
    # a function tag counts only once at least 20 holders were read with it (older reads lack newer tags)
    need = min(20, max(10, int(0.8 * len(ref.rows))))  # in a group of 10-19, at least 80% of holders must have it
    usable = [t for t in wanted if sum(1 for r in ref.rows if t in (r.get("tags") or {})) >= need]
    # Domain fit: domains weighted by how many holders of this role show them (a role's domains, not breadth).
    from .reader import DOMAIN_TAGS

    dom_w = {t: sum(1 for r in ref.rows if float((r.get("tags") or {}).get(t, 0)) > 0) / max(1, len(ref.rows))
             for t in DOMAIN_TAGS}
    seen = {t for r in ref.rows for ra in (r.get("roles_anon") or []) for t in (ra.get("tags") or [])}
    rows = [size_scaled(domain_fit(family_view(with_uq(r, prev), ref.cluster, usable, seen), dom_w)) for r in ref.rows]
    uf = size_scaled(domain_fit(family_view(with_uq(user_f, prev), ref.cluster, usable, seen), dom_w))
    rows, uf, caps = saturate(rows, uf, cap_q)
    M = np.array([_vec(r) for r in rows])
    U = _vec(uf)
    ed_cov = sum(1 for r in rows if r.get("ED") is not None) / len(rows)
    # market weights were measured on Partnerships hires only; other families use the research-based prior alone
    w = hybrid_weights(ref.n if fam == "partnerships" else 0)
    if fam in AD_FAMILIES:  # sides covered matter where the role sells or partners in advertising
        w["SG"] = 8.0
    if ed_cov < 0.5:  # education enters the score only when at least half the holders' education is known
        w["ED"] = 0.0
    pending = {}
    for k, need_k in NEW_FACTORS.items():
        have = sum(1 for r in rows if r.get(k) is not None)
        need_k = min(need_k, max(10, int(0.8 * len(rows))))
        if have < need_k:
            w[k] = 0.0
            pending[k] = {"label": FACTOR_LABELS[k], "holders_with_data": have, "needed": need_k, "you": uf.get(k)}
    tot = sum(w.values()) or 1
    w = {k: 100 * v / tot for k, v in w.items()}  # weights of the factors that count sum to 100
    wv = np.array([w[k] for k in FACTORS])
    P_h, P_u = pct_matrix(M, M), pct_matrix(U[None, :], M)[0]
    for j, k in enumerate(FACTORS):  # at or above the cap = the cap's percentile, not a tie-split above it
        if k in caps:
            P_h[:, j] = np.where(M[:, j] >= caps[k], np.minimum(P_h[:, j], cap_q or 100), P_h[:, j])
            if not np.isnan(U[j]) and U[j] >= caps[k]:
                P_u[j] = min(P_u[j], cap_q or 100)
    S_h, S_u = composite(P_h, wv), float(composite(P_u[None, :], wv)[0])
    # Gates, like a screen: a factor that most holders show (60%+) and you do not show at all caps your score at the
    # median holder's, instead of being averaged away by strengths elsewhere.
    gates = []
    for j, k in enumerate(FACTORS):
        if k not in GATE_FACTORS or w.get(k, 0) <= 0 or np.isnan(U[j]):
            continue
        share = float(np.mean([1.0 if (not np.isnan(v) and v > 0) else 0.0 for v in M[:, j] if not np.isnan(v)])) \
            if np.any(~np.isnan(M[:, j])) else 0.0
        if share >= GATE_SHARE and U[j] <= 0:
            gates.append({"factor": k, "label": FACTOR_LABELS[k], "holder_share": round(share, 2)})
    S_u_ungated = S_u
    if gates:
        S_u = min(S_u, float(np.nanmedian(S_h)))
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
        "cluster": ref.cluster, "n_reference": ref.n,
        "n_read_at_hire": sum(1 for r in ref.rows if r.get("rv") == 2), "weights": {k: _r(v) for k, v in w.items()},
        "base_score": _r(S_u), "score_before_gates": _r(S_u_ungated), "gates": gates, "position": _r(pos),
        "position_ci95": ([_r(min(np.percentile(boots, 2.5), pos)), _r(min(np.percentile(boots, 97.5), pos))] if gates else
                          [_r(np.percentile(boots, 2.5)), _r(np.percentile(boots, 97.5))]) if boots else [None, None],
        "holders": {"scores": sorted(_r(x) for x in sc),
                    "tier_share": {f"Tier {t}": round(sum(1 for r in rows if r.get("tier") == t) / len(rows), 2) for t in (1, 2, 3)},
                    "median": _r(np.median(sc)), "p25": _r(np.percentile(sc, 25)), "p75": _r(np.percentile(sc, 75)),
                    "hist": {"edges": [int(e) for e in edges], "counts": [int(c) for c in hist]}},
        "factors": factors, "pending_factors": pending, "caps": {k: _r(v, 2) for k, v in caps.items()}, "gaps": gaps, "differentiators": leads, "focus_areas": focus, "rare_strengths": rare,
        "prevalence": {t: round(p, 2) for t, p in prevalence.items()}, "tag_labels": TAG_LABELS, "peers": peers,
        "scarcity_prevalence": {t: round(p, 2) for t, p in prev.items()},
        "benchmark": _benchmark(S_u, S_h, P_h, P_u, w, rows, uf, M, wv, prev, caps),
        "cards": _cards(S_u, S_h, P_h, P_u, rows, uf, order),
        "_internal": {"P_u": P_u, "M": M, "wv": wv, "user": uf, "prev": prev, "caps": caps},
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


def _score_with(uf: dict, M: np.ndarray, wv: np.ndarray, prev: dict, caps: dict | None = None) -> tuple[float, float]:
    f = with_uq(uf, prev)
    for k, c in (caps or {}).items():  # the same cap as the holders' values
        if f.get(k) is not None and float(f[k]) > c:
            f[k] = c
    P = pct_matrix(_vec(f)[None, :], M)
    s = float(composite(P, wv)[0])
    return s, position(s, composite(pct_matrix(M, M), wv))


def _benchmark(S_u, S_h, P_h, P_u, w, rows, uf, M, wv, prev, caps=None) -> dict:
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
        s, p = _score_with(alt, M, wv, prev, caps)
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


WHATIF_RANGES = {"YOE": (0, 45), "CT": (1, 4), "LV": (0, 5), "FN": (0, 1), "DM": (0, 1), "AC": (0, 20),
                 "ED": (1, 3), "AI": (0, 1), "TK": (0, 1)}


def what_if(card: dict, changes: dict) -> dict:
    """Rescore with some factor values changed (everything else as read). Values are clipped to valid ranges."""
    it = card["_internal"]
    uf = it["user"]
    applied = {}
    for k, v in (changes or {}).items():
        if k in WHATIF_RANGES and isinstance(v, (int, float)):
            lo, hi = WHATIF_RANGES[k]
            applied[k] = max(lo, min(hi, float(v)))
    if not applied:
        return {"error": f"no valid changes; factors and ranges: {WHATIF_RANGES}"}
    s, p = _score_with({**uf, **applied}, it["M"], it["wv"], it["prev"], it.get("caps"))
    return {"changes": applied, "before": {k: uf.get(k) for k in applied}, "score": _r(s), "position": _r(p),
            "delta": _r(s - card["base_score"]), "base_score": card["base_score"]}
