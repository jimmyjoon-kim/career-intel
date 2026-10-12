"""Shared taxonomy: sector -> role cluster -> level band -> requirement tags.

Requirement tags describe what a candidate must have. Attribute tags (scope, market,
sponsorship, authorisation, tenure) are NOT requirements: they are mapped to posting
fields (scope, no_sponsorship, years_required) and handled by the gate instead.
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tag:
    key: str
    label: str
    group: str
    patterns: tuple[str, ...] = field(default_factory=tuple)
    closable: bool = False  # can a typical candidate close this gap within ~12 months?
    close_hint: str = ""


def _t(key, label, group, patterns=(), closable=False, close_hint=""):
    return Tag(key, label, group, tuple(patterns), closable, close_hint)


TAGS: dict[str, Tag] = {
    t.key: t
    for t in [
        # Domain
        _t("domain_adtech", "Ad tech / advertising platforms", "domain",
           [r"ad ?tech", r"advertis", r"monetiz", r"monetis", r"programmatic", r"\bssp\b", r"\bdsp\b", r"ad network", r"mediation", r"user acquisition"]),
        _t("domain_ai", "AI / ML products", "domain",
           [r"\bai\b", r"artificial intelligence", r"machine learning", r"\bllm", r"generative", r"\bml\b"],
           True, "Ship or commercialise an AI product; AI coursework or certifications count as partial."),
        _t("domain_marketplace", "Marketplace / consumer platforms", "domain",
           [r"marketplace", r"e-?commerce", r"delivery", r"two-sided"]),
        _t("domain_mobile", "Mobile apps / gaming", "domain",
           [r"mobile", r"\bapps?\b", r"gaming", r"games?\b", r"app store"]),
        _t("domain_saas", "B2B SaaS", "domain",
           [r"\bsaas\b", r"software as a service", r"\bb2b\b", r"enterprise software", r"subscription"], True,
           "Commercial work with a B2B software product."),
        _t("domain_other", "Industry outside your core domains (e.g. semiconductors, payments)", "domain", []),
        # Function
        _t("func_ad_sales", "Advertising sales", "function",
           [r"ad sales", r"advertising sales", r"advertiser", r"agency", r"brand partnerships", r"media sales"]),
        _t("func_alliances_gsi", "Alliances with GSIs / consultancies", "function",
           [r"alliance", r"\bgsi", r"system integrator", r"accenture", r"deloitte", r"mckinsey", r"pwc"]),
        _t("func_bd", "Business development", "function",
           [r"business development", r"\bbd\b", r"new business", r"partnership development"]),
        _t("func_channel", "Channel / reseller programmes", "function",
           [r"channel", r"reseller", r"distribution partner"]),
        _t("func_growth", "Growth (revenue growth ownership)", "function",
           [r"\bgrowth\b"]),
        _t("func_growth_marketing", "Growth marketing", "function",
           [r"growth marketing", r"lifecycle marketing", r"demand gen"], True),
        _t("func_partnerships", "Partnerships", "function",
           [r"partnership", r"partner"]),
        _t("func_product_strategy", "Product strategy", "function",
           [r"product strategy", r"product management", r"roadmap"], True),
        _t("func_rev_strategy", "Revenue strategy & operations", "function",
           [r"revenue strategy", r"rev ?ops", r"revenue operations", r"sales strategy", r"go-to-market", r"\bgtm\b", r"business planning"], True,
           "Own planning, forecasting or GTM design explicitly; reframe existing P&L leadership."),
        _t("func_sales_leadership", "Sales leadership", "function",
           [r"head of sales", r"sales leader", r"vp,? sales", r"sales director", r"general manager", r"\bgm\b", r"country manager", r"managing director", r"\bcro\b", r"chief revenue"]),
        # Management / scale
        _t("team_mgmt", "People management", "management",
           [r"managed a team", r"led a team", r"team of", r"direct reports", r"built (?:and led )?(?:a|the) team", r"hired", r"general manager", r"head of"]),
        _t("team_large", "Large team / org leadership", "management",
           [r"\b(?:[2-9]\d|\d{3,})\+? (?:people|staff|employees|reports)", r"team of (?:[2-9]\d|\d{3,})", r"organisation of", r"organization of", r"multi-team"]),
        _t("mgmt_tenure_stated", "Stated years of people management", "management",
           [r"years? of (?:people )?management", r"managing teams for"]),
        _t("pnl_ownership", "P&L ownership", "management",
           [r"p&l", r"p and l", r"profit and loss", r"profit", r"revenue of", r"\$\d+(?:\.\d+)?\s?(?:m|mm|million|b|bn|billion)"]),
        # Education
        _t("edu_bachelors", "Bachelor's degree", "education",
           [r"bachelor", r"\bb\.?s\.?c?\b", r"\bb\.?a\.?\b", r"\bbeng\b", r"undergraduate", r"university"]),
        _t("edu_technical", "Technical degree", "education",
           [r"engineering", r"computer science", r"\bstem\b", r"technical degree"]),
        # Skills
        _t("skill_0to1_build", "0→1 business building", "skill",
           [r"founded", r"co-?founder", r"launched", r"built (?:the )?business", r"from scratch", r"0 ?(?:to|→) ?1", r"start-?up"]),
        _t("skill_consulting_firm_background", "Management-consulting background", "skill",
           [r"mckinsey", r"bain", r"\bbcg\b", r"consulting firm", r"management consult"],
           False, "Not closable by experience; offset with strategy credentials (EMBA) and structured problem-solving evidence."),
        _t("skill_cosell", "Co-sell motions with partners", "skill",
           [r"co-?sell", r"joint go-to-market", r"partner-led"], True),
        _t("skill_deal_structuring", "Deal structuring / negotiation", "skill",
           [r"deal", r"negotiat", r"contract", r"term sheet", r"revenue share", r"rev-?share"]),
        _t("skill_enterprise_sales", "Enterprise sales", "skill",
           [r"enterprise", r"strategic accounts", r"key accounts", r"large customers"]),
        _t("skill_exec_presence", "Executive presence / C-level relationships", "skill",
           [r"c-?level", r"c-?suite", r"executive", r"board", r"ceo", r"senior leadership"]),
        _t("skill_forecasting_crm", "Forecasting / pipeline / CRM", "skill",
           [r"forecast", r"pipeline", r"salesforce", r"\bcrm\b", r"quota"]),
        _t("skill_govtech", "Government / public sector", "skill",
           [r"government", r"public sector", r"federal"]),
        _t("skill_hyperscaler", "Hyperscaler partnerships (AWS/GCP/Azure)", "skill",
           [r"\baws\b", r"amazon web services", r"\bgcp\b", r"google cloud", r"azure", r"hyperscaler"], True),
        _t("skill_licensing_ip", "Content / IP licensing", "skill",
           [r"licens", r"\bip\b", r"intellectual property", r"rights"], True),
        _t("skill_llm_ai_products", "Hands-on with LLM / AI products", "skill",
           [r"\bllm", r"large language model", r"\brag\b", r"agent", r"prompt", r"gpt", r"claude"], True,
           "Build and demo an LLM product (this platform counts) or complete applied AI coursework."),
        _t("skill_measurement_attribution", "Measurement / attribution", "skill",
           [r"measurement", r"attribution", r"\bmmp\b", r"incrementality", r"roas"]),
        _t("skill_payments", "Payments", "skill", [r"payment", r"fintech", r"checkout"]),
        _t("skill_performance_marketing", "Performance marketing", "skill",
           [r"performance marketing", r"user acquisition", r"\bua\b", r"cpi\b", r"roas"]),
        _t("skill_programmatic", "Programmatic", "skill",
           [r"programmatic", r"rtb", r"real-time bidding", r"exchange", r"bidding"]),
        _t("skill_retail_media", "Retail media", "skill", [r"retail media", r"commerce media"], True),
        _t("skill_sdk_api", "SDK / API products", "skill", [r"\bsdk", r"\bapi", r"developer platform", r"integration"]),
        _t("skill_si_gsi", "Systems-integrator relationships", "skill",
           [r"system integrator", r"\bsi\b", r"\bgsi", r"accenture", r"deloitte", r"infosys", r"wipro", r"cognizant"], True),
        _t("skill_startup_ecosystem", "Start-up / VC ecosystem", "skill",
           [r"start-?up", r"venture", r"\bvc\b", r"accelerator"]),
        _t("skill_vertical_industry", "Vertical industry expertise", "skill",
           [r"vertical", r"cpg", r"retail", r"automotive", r"financial services", r"healthcare"], True),
        _t("skill_demand_gen", "Demand generation", "skill", [r"demand gen", r"lead gen", r"marketing qualified"], True),
    ]
}

# Tags that are attributes of the posting, not requirements of the candidate.
ATTRIBUTE_TAG_PREFIXES = ("scope_", "market_", "tenure_")
ATTRIBUTE_TAGS = {"sponsorship_available", "auth_required"}

TENURE_YEARS = {
    "tenure_5plus": 5, "tenure_8plus": 8, "tenure_10plus": 10,
    "tenure_12plus": 12, "tenure_15plus": 15, "tenure_20plus": 20,
}

ROLE_CLUSTERS = ["Partnerships", "Ad Sales", "Sales Leadership", "Growth", "Rev Strategy", "GM / Business Lead", "Other"]

# Level ladder; "Head" is treated as Director-equivalent.
LEVELS = ["IC", "Manager", "Senior Manager", "Director", "Head", "Sr Director", "VP", "SVP", "C-level"]
LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}
LEVEL_RANK["Head"] = LEVEL_RANK["Director"]


def is_requirement_tag(tag: str) -> bool:
    return tag not in ATTRIBUTE_TAGS and not tag.startswith(ATTRIBUTE_TAG_PREFIXES)


def split_tags(raw_tags: list[str]) -> tuple[list[str], dict]:
    """Split a raw tag list into (requirement tags, attributes)."""
    reqs, attrs = [], {"scope": "", "years_required": None, "sponsorship_available": False, "auth_required": False}
    for t in raw_tags:
        if t in TENURE_YEARS:
            attrs["years_required"] = max(attrs["years_required"] or 0, TENURE_YEARS[t])
        elif t.startswith("scope_"):
            attrs["scope"] = t.removeprefix("scope_")
        elif t in ATTRIBUTE_TAGS:
            attrs[t] = True
        elif is_requirement_tag(t):
            reqs.append(t)
    return sorted(set(reqs)), attrs


def infer_level(title: str) -> str:
    t = title.lower()
    rules = [
        (r"\b(chief|cro|ceo|coo)\b", "C-level"),
        (r"\b(svp|senior vice president|evp)\b", "SVP"),
        (r"\b(vp|vice president)\b", "VP"),
        (r"\b(senior director|sr\.? director)\b", "Sr Director"),
        (r"\bhead of\b|\bgeneral manager\b", "Head"),
        (r"\bdirector\b", "Director"),
        (r"\bsenior manager\b|\bsr\.? manager\b", "Senior Manager"),
        (r"\bmanager\b|\blead\b", "Manager"),
    ]
    for pat, lvl in rules:
        if re.search(pat, t):
            return lvl
    return "IC"


def keyword_tags(text: str) -> dict[str, str]:
    """Offline tag detection. Returns {tag: evidence snippet} for tags whose patterns appear."""
    found: dict[str, str] = {}
    low = text.lower()
    for tag in TAGS.values():
        for pat in tag.patterns:
            m = re.search(pat, low)
            if m:
                start, end = max(0, m.start() - 60), min(len(text), m.end() + 60)
                found[tag.key] = " ".join(text[start:end].split())
                break
    return found


def taxonomy_for_prompt() -> str:
    return "\n".join(f"- {t.key}: {t.label}" for t in TAGS.values())
