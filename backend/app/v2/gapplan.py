"""Gap plan: every shortfall against (1) the median role holder, (2) the holders who score above you,
(3) the requirements of open postings that pass your gate, with how to close it, time, and score effect."""

from __future__ import annotations

from ..taxonomy import TAGS

# How to close each kind of gap. Stated as conditions on facts, never as claims about the user.
FACTOR_ACTIONS = {
    "CT": ("Hold a role for 12+ months at a Tier 1 or Tier 2 employer, or take part in a company's IPO or acquisition "
           "(joined 6+ months before it). Lead with the strongest employer record you have.", 24),
    "FN": ("If you ran partnership, business development or channel/reseller work in a role that ended in the last 8 years, "
           "say so in that role's description or confirm it on Role review; work older than 8 years counts half.", 1),
    "LV": ("Hold a higher band for 12+ months.", 18),
    "YOE": ("Time in role; 12 months per year of difference.", None),
    "DM": ("If you did commercial work in the missing domain (AI, SaaS, ad tech, mobile), state it in the role description; "
           "otherwise 6–12 months of such work.", 9),
    "UQ": ("Scarce experience such as hyperscaler co-sell, GSI alliances, government or a 0-to-1 build: state it if done, "
           "otherwise 6–12 months.", 9),
    "AC": ("Write quantified outcomes (revenue, growth %, team size, partner count) into role descriptions.", 1),
    "AI": ("Commercial work on an AI product, at an AI company or with AI partners, active within the last 24 months; "
           "or an AI graduate degree. AI work older than about two years counts very little.", 6),
    "TK": ("Technical product work (SDK/API, platform, ML) written into a recent role, a technical role, or a technical degree.", 6),
    "ED": ("Complete a graduate degree (master's or MBA); it counts from its completion date. "
           "A degree in progress is listed on the Scorecard and counts automatically once its end date passes.", 24),
}
TAG_ACTIONS = {
    "func_channel": ("If channel, reseller or partner-sales work was part of a role since 2018, add it to that role or confirm it on Role review.", 1),
    "domain_saas": ("If you sold or partnered on a SaaS or cloud product, state it in that role; otherwise 6–12 months of such work.", 9),
    "skill_hyperscaler": ("A co-sell, marketplace or partnership programme with AWS, Google Cloud or Azure; 6–12 months.", 9),
    "skill_govtech": ("Public-sector commercial work; 12+ months. Relevant mainly to government-facing roles.", 12),
    "skill_consulting_firm_background": ("Employment at a consulting firm; not closable through current work. "
                                          "Strategy coursework (EMBA) is partial evidence only.", None),
    "skill_0to1_build": ("State a business or function you built from zero.", 1),
}


def _closable(months: int | None, left: int | None) -> bool | None:
    if months is None:
        return False
    if left is None:
        return None
    return months <= left


def build_gap_plan(card: dict, posting_gaps: list[dict], months_left: int | None, ed_months: int | None = None) -> list[dict]:
    """ed_months: months until your next graduate degree in progress completes (None if none)."""
    items: list[dict] = []
    actions = dict(FACTOR_ACTIONS)
    if ed_months is not None:
        actions["ED"] = ("Your graduate degree in progress counts from its completion date; nothing else to do.", ed_months)
    whatif = {w["factor"]: w for w in card.get("benchmark", {}).get("whatifs", [])}
    # 1. Against the median holder
    for g in card["gaps"]:
        action, months = actions[g["factor"]]
        wf = whatif.get(g["label"])
        items.append({"against": "Median role holder", "gap": g["label"], "kind": g["class"],
                      "you": g["you_value"], "them": g["holder_median_value"],
                      "evidence": f'{round(100 * (g["share_above_you"] or 0))}% of holders are above you; weighted gap +{g["delta"]} points.',
                      "action": action, "months": months, "by_target": _closable(months, months_left),
                      "score_effect": wf["delta"] if wf else None, "factor": g["factor"]})
    # 2. Against holders who score above you
    seen = {i["gap"] for i in items}
    for d in card.get("benchmark", {}).get("drivers", []):
        if (d["avg_points"] or 0) > 0.5 and d["label"] not in seen:
            k = next(f["factor"] for f in card["factors"] if f["label"] == d["label"])
            action, months = actions[k]
            wf = whatif.get(d["label"])
            items.append({"against": f'{card["benchmark"]["n_above"]} holders who score above you', "gap": d["label"],
                          "kind": "structural" if k in ("CT", "LV", "YOE") else "capability",
                          "you": next(f["you_value"] for f in card["factors"] if f["factor"] == k), "them": None,
                          "evidence": f'{d["holders_ahead"]} of them lead you here, by {d["avg_points"]} points on average.',
                          "action": action, "months": months, "by_target": _closable(months, months_left),
                          "score_effect": wf["delta"] if wf else None, "factor": k})
    # 3. Qualifications common among holders that are missing or older in your record
    for f in card.get("focus_areas", []):
        action, months = TAG_ACTIONS.get(f["tag"], ("State it in a role description if done.", 9))
        items.append({"against": "Role holders' qualifications", "gap": f["label"], "kind": "capability" if months else "structural",
                      "you": f["status"], "them": f'{round(100 * f["holder_share"])}% of holders',
                      "evidence": f'{round(100 * f["holder_share"])}% of holders have it; yours is {f["status"]}.',
                      "action": action, "months": months, "by_target": _closable(months, months_left),
                      "score_effect": None, "factor": None})
    # 4. Requirements of open postings that pass your gate
    for g in posting_gaps[:6]:
        t = TAGS.get(g["tag"])
        hint = (t.close_hint if t and t.close_hint else
                ("State it in a role description or set it on Profile if you have it." if (t and t.closable) else
                 "Not readily closable; check whether your record already shows it and set it on Profile."))
        items.append({"against": "Open postings' requirements", "gap": g["label"], "kind": "hard minimum" if g.get("hard") else "requirement",
                      "you": {1.0: "Has", 0.5: "Partial"}.get(g["match"], "Missing"), "them": f'{g["postings"]} postings',
                      "evidence": f'Asked for by {g["postings"]} postings that pass your gate ({g["cls"].lower()}).',
                      "action": hint, "months": 6 if (t and t.closable) else None,
                      "by_target": _closable(6 if (t and t.closable) else None, months_left), "score_effect": None, "factor": None})
    return items
