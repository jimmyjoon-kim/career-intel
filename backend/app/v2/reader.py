"""Full-text experience reader (v2).

Reads every role's title, company, dates and description lines, then derives the scoring
factors with the SAME deterministic rules for the user and for every reference holder.
Titles alone never decide function or domain: descriptions are read too, and each matched
phrase is kept as evidence.

Input formats
  1. LinkedIn "Experience" text (copy of the experience page): a standalone date line
     ("Jan 2016 - Mar 2025 · 9 yrs 3 mos") anchors each role; title/company are the lines above.
  2. CV-style text: a date range anywhere on a line ("ironSource | GM | Jan 2016 – Mar 2025").

No age or age proxy is read. No probabilities are produced.
"""

from __future__ import annotations

import re
from datetime import date

# ------------------------------------------------------------------ dates
MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_M = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE_RE = re.compile(rf"^((?:{_M} )?\d{{4}}) [-–] ((?:{_M} )?\d{{4}}|Present)(?: · .*)?$")
INLINE_DATE = re.compile(rf"((?:{_M}\s+)?(?:19|20)\d{{2}})\s*(?:[-–—]|to)\s*((?:{_M}\s+)?(?:19|20)\d{{2}}|Present|Current|Now)", re.I)
TYPES = r"Full-time|Part-time|Contract|Freelance|Self-employed|Internship|Temporary|Apprenticeship|Seasonal"
TYPE_LINE = re.compile(rf"^({TYPES})$")
CO_TYPE_LINE = re.compile(rf"^(.+?) · ({TYPES})$")
GROUP_DUR = re.compile(rf"^(?:(?:{TYPES}) · )?\d+ (?:yrs?|mos?)(?: \d+ mos?)?$")
TITLE_WORDS = re.compile(
    r"director|manager|head|vp|vice president|president|chief|lead|officer|partner|sales|engineer|consultant|executive|"
    r"analyst|associate|specialist|founder|principal|gm\b|general manager|strategist|coordinator|assistant|intern|advisor|"
    r"member|producer|representative|scientist|architect|planner|supervisor|development|partnerships|business", re.I)
SKIP_LINE = re.compile(r"^(Skills: |Show all \d|Load more$|Experience$|Hybrid$|Remote$|On-site$|.* · (Hybrid|Remote|On-site)$|\s*$)")
CV_PREFIX = "<<CV>> "


def _now() -> tuple[int, int]:
    d = date.today()
    return (d.year, d.month)


def _ym(s: str, now: tuple[int, int]) -> tuple[int, int | None]:
    s = s.strip()
    if s.lower() in ("present", "current", "now"):
        return now
    p = s.replace(".", "").split()
    if len(p) == 2:
        return (int(p[1]), MON[p[0][:3].lower()])
    return (int(p[0]), None)


def months_between(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


def _finish(role: dict, now: tuple[int, int]) -> dict:
    s, e = _ym(role["start_raw"], now), _ym(role["end_raw"], now)
    if s[1] is None:
        s = (s[0], 1)
    if e[1] is None:
        e = (e[0], 12) if e[0] < now[0] else now
    role["start"], role["end"] = s, e
    role["months"] = max(0, months_between(s, e)) + 1  # LinkedIn counts months inclusively
    return role


def parse_linkedin(text: str, now: tuple[int, int] | None = None) -> list[dict]:
    now = now or _now()
    L = [ln.rstrip() for ln in text.split("\n") if ln.strip()]
    date_idx = [i for i, ln in enumerate(L) if DATE_RE.match(ln)]
    roles, group = [], None
    for n, i in enumerate(date_idx):
        prev_i = date_idx[n - 1] if n else -1
        for j in range(prev_i + 1, i):
            if j + 1 < i and GROUP_DUR.match(L[j + 1]) and not DATE_RE.match(L[j]) and not TYPE_LINE.match(L[j]):
                group = L[j]
        prev = L[i - 1] if i >= 1 else ""
        prev2 = L[i - 2] if i >= 2 else ""
        emp_type = None
        m = CO_TYPE_LINE.match(prev)
        if m:
            company, title, emp_type = m.group(1), prev2, m.group(2)
            group, tstart = None, i - 2
        elif TYPE_LINE.match(prev):
            emp_type, title, company, tstart = prev, prev2, group or "", i - 2
        elif group:
            if (not TITLE_WORDS.search(prev) and len(prev.split()) <= 4 and TITLE_WORDS.search(prev2)
                    and not DATE_RE.match(prev2)):
                title, company, tstart = prev2, prev, i - 2
            else:
                title, company, tstart = prev, group, i - 1
        else:
            title, company, tstart = prev2, prev, i - 2
            if not prev2 or DATE_RE.match(prev2) or SKIP_LINE.match(prev2):
                title, company, tstart = prev, "", i - 1
        dm = DATE_RE.match(L[i])
        roles.append({"title": title.strip(), "company": company.strip(), "emp_type": emp_type,
                      "start_raw": dm.group(1), "end_raw": dm.group(2), "_date_i": i, "_tstart": tstart})
    for n, r in enumerate(roles):
        stop = roles[n + 1]["_tstart"] if n + 1 < len(roles) else len(L)
        desc = []
        for j in range(r["_date_i"] + 1, stop):
            ln = L[j]
            if SKIP_LINE.match(ln) or GROUP_DUR.match(ln) or (j + 1 < stop and GROUP_DUR.match(L[j + 1])):
                continue
            desc.append(ln)
        r["desc"] = desc
        r.pop("_date_i"), r.pop("_tstart")
        _finish(r, now)
    return roles


def parse_inline(text: str, now: tuple[int, int] | None = None) -> list[dict]:
    """CV-style text: each line carrying a date range starts a role."""
    now = now or _now()
    L = [ln.strip() for ln in text.split("\n") if ln.strip()]
    roles: list[dict] = []
    for i, ln in enumerate(L):
        m = INLINE_DATE.search(ln)
        if not m:
            if roles:
                roles[-1]["desc"].append(ln.lstrip("-•* ").strip())
            continue
        head = (ln[: m.start()] + " " + ln[m.end():]).strip(" |,·—–-()\t")
        parts = [p.strip() for p in re.split(r"\s*[|·,—–]\s*|\s{2,}", head) if p.strip()]
        if not parts and i >= 1:
            parts = [p.strip() for p in re.split(r"\s*[|·,—–]\s*", L[i - 1]) if p.strip()]
            if roles and roles[-1]["desc"] and roles[-1]["desc"][-1] == L[i - 1].lstrip("-•* ").strip():
                roles[-1]["desc"].pop()
        titled = [p for p in parts if TITLE_WORDS.search(p)]
        title = titled[0] if titled else (parts[0] if parts else "")
        company = next((p for p in parts if p != title), "")
        roles.append(_finish({"title": title, "company": company, "emp_type": None,
                              "start_raw": m.group(1), "end_raw": m.group(2), "desc": []}, now))
    return roles


def parse_roles(text: str, now: tuple[int, int] | None = None) -> tuple[list[dict], str]:
    if not text or not text.strip():
        return [], "empty"
    li = parse_linkedin(text, now)
    if li:
        return li, "linkedin"
    return parse_inline(text, now), "inline"


# ------------------------------------------------------------------ rules
EXCL_EVIDENCE = re.compile(r"\bintern\b|internship|\bstudent\b", re.I)  # never counts
EXCL_COUNT = re.compile(r"advis|board member|guest speaker|volunteer|fellow|co organizer|^member\b|career break|^travel$", re.I)
EXCL_TYPES = {"Part-time", "Freelance", "Internship"}
OPERATING = re.compile(r"\b(chief|cro|ceo|coo|cso|cmo|vp|vice president|director|head of|general manager|gm|manager|president)\b", re.I)

# Level bands: 0 IC/Manager, 1 Director, 2 Head / Sr Director / GM, 3 VP, 4 SVP/EVP/MD, 5 C-level
LEVEL = [
    (r"\b(chief|cro|ceo|coo|cso|cmo|cpo|(?<!vice )(?<!vice-)president)\b", 5),
    (r"\b(svp|evp|senior vice president|executive vice president|managing director)\b", 4),
    (r"\b(vp|vice president|avp|rvp)\b", 3),
    (r"\b(senior director|sr\.? director|global head|head of|general manager|gm\b|group director)", 2),
    (r"\bdirector\b", 1),
    (r"\b(senior manager|sr\.? manager|lead|principal|consultant|specialist|account executive|manager|associate|analyst|"
     r"engineer|scientist|representative|planner|coordinator|assistant|strategist|producer|officer)\b", 0),
]
LEVEL_NAMES = {0: "Manager / IC", 1: "Director", 2: "Head / Sr Director / GM", 3: "VP", 4: "SVP / MD", 5: "C-level"}
LEVEL_CUES = re.compile(r"\bp&l\b|\bpnl\b|p&l responsib|managed p&l|owned (?:full )?p&l|led [^.]{0,40}(organization|org\b)|"
                        r"\bhead of\b|general manager|business unit|led the [^.]{0,30}business\b", re.I)
STAFF_PHRASES = re.compile(r"office of the (?:ceo|coo|cro|chairman)|chief of staff|business lead to the \w+|aide to|"
                           r"to the (?:ceo|coo|cro|svp|vp)\b", re.I)

TAGPAT = {
    "func_partnerships": r"partner|alliance",
    "func_bd": r"business development|\bbd\b",
    "func_channel": r"\bchannel|reseller|partner sales|\bvar\b|distributor|\bgsi\b|system integrator",
    "domain_adtech": r"ad tech|adtech|\bads?\b|advertis|monetiz|monetis|programmatic|\bdsp\b|\bssp\b|mediation|"
                     r"taboola|openx|pubmatic|trade desk|moloco|liftoff|inmobi|stackadapt|liveramp|offerwall|retail media|\bctv\b|media buying",
    "domain_ai": r"\bai\b|\ba\.i\.\b|openai|anthropic|genai|gen ai|generative|\bllm|character\.ai|xai|copilot|gemini|bedrock|"
                 r"machine learning|\bml\b|agentic|ai[- ]powered",
    "domain_saas": r"saas|okta|salesforce|jfrog|datadog|crowdstrike|pandadoc|wiz\b|\bisv|cloud|enterprise software|slack|dropbox|"
                   r"zendesk|asana|hubspot",
    "domain_mobile": r"mobile|\bapp\b|\bapps\b|gaming|games?\b|roblox|epic games|xbox|app store|\bios\b|android|playstation|nintendo|publisher",
    "skill_hyperscaler": r"\baws\b|amazon web services|google cloud|\bgcp\b|azure|hyperscaler|bedrock",
    "skill_govtech": r"government|federal|public sector|\bnavy\b|defense|anduril|national security|\bdod\b|military",
    "skill_0to1_build": r"founder|co-founder|fractional|\bceo\b|incubat|from scratch|from inception|from the ground up|from zero|"
                        r"first (?:commercial|business development|bd) hire|founding (?:team|member)|launched (?:the )?(?:korea|business|a new|new) |"
                        r"stood up|built (?:and led |and scaled )?(?:the |a )?[^.]{0,30}(?:function|team|program|business|operation)",
}
# Consulting background = worked AT a consulting firm (employer field) or described management/strategy consulting work.
# A "Consultant" job title elsewhere, or a consulting firm named as a client or partner, does not count.
CONSULTING_FIRMS = re.compile(
    r"\b(mckinsey|bain|bcg|boston consulting|deloitte|accenture|pwc|pricewaterhouse|kpmg|ernst & young|\bey\b|ey-parthenon|"
    r"alvarez|oliver wyman|kearney|slalom|booz|l\.e\.k|capgemini|roland berger|strategy&)", re.I)
CONSULTING_WORK = re.compile(r"management consult|strategy consult|consulting firm|consulting practice", re.I)
CONSULTING = "skill_consulting_firm_background"

FUNC_TAGS = ["func_partnerships", "func_bd", "func_channel"]
DOMAIN_TAGS = ["domain_ai", "domain_adtech", "domain_mobile", "domain_saas"]
SCARCE_TAGS = ["skill_hyperscaler", "skill_govtech", CONSULTING, "skill_0to1_build", "domain_mobile"]
# Role templates: the qualifications a title family carries by default. Applied to every person
# (marked "implied by title"); users review and adjust their own roles.
ROLE_TEMPLATES = [
    ("General manager / business-unit head",
     r"general manager|\bgm\b|managing director|country manager|head of (?:the )?(?:business|country|region|operations)",
     ["team_mgmt", "pnl_ownership", "func_sales_leadership"]),
    ("Chief executive / president", r"\bceo\b|chief executive|(?<!vice )(?<!vice-)president",
     ["team_mgmt", "pnl_ownership", "func_sales_leadership"]),
    ("Chief revenue / commercial officer", r"\bcro\b|chief revenue|chief commercial|chief business|\bcco\b",
     ["team_mgmt", "func_sales_leadership"]),
    ("Vice president", r"vice president|\bvp\b|\bsvp\b|\bevp\b", ["team_mgmt"]),
    ("Sales leader", r"vp,? (?:of )?sales|head of sales|sales director|director,? (?:of )?sales", ["func_sales_leadership"]),
    ("Channel management", r"channel|reseller|distribution", ["func_channel", "func_partnerships"]),
    ("Partner / alliance management", r"partner|alliance", ["func_partnerships"]),
    ("Business development", r"business development|\bbd\b|bizdev", ["func_bd"]),
    ("Founder", r"\bfounder|co-founder|cofounder", ["skill_0to1_build", "team_mgmt"]),
]
ROLE_TEMPLATES = [(n, re.compile(p, re.I), t) for n, p, t in ROLE_TEMPLATES]
# Responsibilities read from description lines.
SCOPE_PAT = {
    "team_mgmt": r"\b(?:led|managed|manage|managing|oversaw|overseeing|built and led|built and managed|leading)\b[^.;]{0,60}"
                 r"\b(?:team|teams|organi[sz]ation|org|department|staff|people|engineers|managers|sales force)\b|direct reports|"
                 r"overseeing (?:business development|account management|operations|sales)|cross-functional team",
    "pnl_ownership": r"p&l|profit and loss|net profit|revenue budget",
    "func_sales_leadership": r"head of sales|sales leadership|led (?:the )?[^.;]{0,30}sales (?:team|organi[sz]ation)|"
                             r"full (?:b2b and b2c )?sales ownership|revenue ownership",
}
TEAM_NUM = re.compile(r"(\d{1,4})\s*\+?\s*(?:business |sales |commercial |engineering |product |operations |account )?"
                      r"(?:people|persons|staff|employees|engineers|product managers|pms?|reports|direct reports|headcount|"
                      r"members|sellers|account managers|managers|business people|fte)\b", re.I)
LARGE_TEAM = 20  # same threshold as the posting taxonomy's "large team" tag

# Employer context from public sources: what the business did, applied to every role at that employer (all people).
COMPANY_CONTEXT = [
    (r"\bunity\b", ["domain_adtech", "domain_mobile"],
     "Unity Grow Solutions: ads and monetisation for games and apps (Q2 2023 revenue $340M)", "https://wnhub.io/news/engines/item-41442"),
    (r"ironsource", ["domain_adtech", "domain_mobile"],
     "ironSource: app monetisation and ad network; NYSE listing June 2021 at $11.1B", "https://en.globes.co.il/en/article-ironsource-to-list-on-nyse-next-week-at-111b-valuation-1001375578"),
    (r"fiksu|bidmind", ["domain_adtech", "domain_mobile"],
     "Fiksu: Boston mobile app marketing technology with a programmatic DSP", "https://www.globenewswire.com/news-release/2013/10/30/1033585/0/en/Fiksu-Extends-App-Marketing-Leadership-With-New-Product-Lineup.html"),
    (r"tapjoy|applovin|liftoff|vungle|chartboost|digital turbine|appsflyer|\badjust\b|inmobi|moloco|unity ads", ["domain_adtech", "domain_mobile"],
     "Mobile ad tech company", ""),
    (r"blackberry|research in motion", ["domain_mobile"], "BlackBerry: smartphones and mobile software", ""),
    (r"openai|anthropic|cohere|mistral|hugging ?face|scale ai|perplexity|character\.ai|\bxai\b", ["domain_ai"], "AI model company", ""),
]
SOURCE_ORDER = {"you confirmed": -1, "title": 0, "employer name": 0, "description": 1, "CV": 2, "stated": 3, "implied by title": 4, "employer context": 5}

ALL_TAGS = list(TAGPAT) + [CONSULTING, "team_mgmt", "team_large", "pnl_ownership", "func_sales_leadership"]

ACH_PAT = re.compile(
    r"\$\s?\d|\d+(?:\.\d+)?\s?%|\b(?:[5-9]|six|seven|eight|nine)[- ]figure|"
    r"\b\d{1,4}\+?\s?(?:people|person|direct reports|reports|partners|headcount|employees|members|clients|customers|accounts|"
    r"studios|sellers|team members|professionals|engineers)\b|\b\d+(?:\.\d+)?x\b|\d{2,3}%? of (?:quota|plan|target)|"
    r"quota in excess|\bmulti-billion|\b\d+\s?(?:M|MM|B|bn|k)\b|\b(?:\d{1,3},)+\d{3}\b", re.I)

# ------------------------------------------------------------------ company tier at time of employment
# T1 = top-10 tech by market cap; T2 = >= $10B public or a dated unicorn / Cloud 100; T3 = other.
# Rule-based list; entries are not checked against a dated market-cap table (stated in the UI).
TIER1 = ["meta", "facebook", "oculus", "microsoft", "google", "youtube", "alphabet", "amazon", "aws", "apple", "nvidia",
         "tiktok", "bytedance"]
TIER2 = ["snap", "reddit", "okta", "salesforce", "adobe", "crowdstrike", "palo alto", "uber", "roblox", "discord", "the trade desk",
         "pinterest", "epic games", "moloco", "character.ai", "xai", "writer", "pandadoc", "anduril", "tech mahindra", "nbcuniversal",
         "comcast", "wiz", "jfrog", "sprout", "paramount", "life360", "taboola", "pubmatic", "stackadapt", "openx", "treasure data",
         "initiative", "ipg", "jiostar", "playfly", "captivate", "oracle", "ibm", "electronic arts", "verizon", "shell", "chase",
         "jpmorgan", "directv", "warnermedia", "own company", "lacework", "mediahub", "nike", "disney", "visa", "american express",
         "wells fargo", "slack", "dropbox", "zendesk", "asana", "linkedin", "tata consultancy", "wolters kluwer", "blackberry",
         "unity", "ironsource", "magic leap", "peloton", "netapp", "orange", "deutsche bank", "blackrock", "cbs", "viacom", "omd",
         "emc", "vmware", "pure storage", "openai", "anthropic", "databricks", "stripe", "autodesk", "intel", "cisco", "samsung"]
STRICT_KEEP_T2 = ["salesforce", "adobe", "crowdstrike", "palo alto", "uber", "roblox", "the trade desk", "pinterest", "nbcuniversal",
                  "comcast", "oracle", "ibm", "electronic arts", "verizon", "shell", "chase", "jpmorgan", "nike", "disney", "visa",
                  "american express", "wells fargo", "linkedin", "tata consultancy", "deutsche bank", "blackrock", "orange",
                  "openai", "anthropic", "databricks", "stripe", "autodesk", "intel", "cisco", "samsung", "vmware"]
T3_FORCE = ["self-employed", "various startups", "freelance", "independent", "fractional"]


def _has(name: str, keys: list[str]) -> bool:
    return any(re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", name) for k in keys)


def company_tier(name: str, strict: bool = False) -> int:
    n = (name or "").lower().strip()
    if not n or _has(n, T3_FORCE):
        return 3
    if _has(n, TIER1):
        return 1
    if _has(n, TIER2):
        if strict and not _has(n, STRICT_KEEP_T2):
            return 3
        return 2
    return 3


def title_level(t: str) -> int | None:
    t = STAFF_PHRASES.sub("", (t or "").lower())  # staff-to-executive phrases do not confer the executive's band
    for pat, lv in LEVEL:
        if re.search(pat, t):
            return lv
    return None


def role_level(r: dict) -> tuple[int | None, str | None]:
    lv = title_level(r["title"])
    cue = LEVEL_CUES.search(" ".join(r["desc"]))
    if cue and (lv is None or lv < 2):
        return 2, cue.group(0)
    return lv, None


def _label(r: dict) -> str:
    return f'{r["title"]} @ {r["company"]} ({r["start_raw"]}–{r["end_raw"]})'


def _line_src(line: str) -> tuple[str, str]:
    if line.startswith(CV_PREFIX):
        return line[len(CV_PREFIX):], "CV"
    if line.lower().startswith("scope:"):
        return line[6:].strip(), "stated"
    return line, "description"


def team_size(lines: list[str]) -> tuple[int, str]:
    """Largest team stated on one line (numbers on the same line are added: '15 business people and 20+ engineers')."""
    best, best_line = 0, ""
    for ln in lines:
        n = sum(int(m.group(1)) for m in TEAM_NUM.finditer(ln))
        if n > best:
            best, best_line = n, ln
    return best, best_line


def role_key(r: dict) -> str:
    return f'{r["company"].strip().lower()}|{r["title"].strip().lower()}|{r["start_raw"]}'


def extract_features(roles: list[dict], *, destination_company: str | None = None, use_cv_lines: bool = True,
                     min_months: int = 12, strict_tier: bool = False, now: tuple[int, int] | None = None,
                     overrides: dict | None = None) -> dict:
    """Factor values from parsed roles. Same rules for everyone."""
    now = now or _now()
    evidence, counted, ev_roles = [], [], []
    for r in roles:
        pairs = [_line_src(d) for d in r["desc"] if use_cv_lines or not d.startswith(CV_PREFIX)]
        r = dict(r, desc=[t for t, _ in pairs], desc_src=[src for _, src in pairs])
        if EXCL_EVIDENCE.search(r["title"]):
            continue
        if destination_company and r["start"] >= (now[0], 1) and \
                destination_company.lower().split()[0].strip("(),") in (r["company"] + " " + r["title"]).lower():
            continue  # the seat a holder was hired into does not count toward their own record
        ev_roles.append(r)
        if r["emp_type"] in EXCL_TYPES or (EXCL_COUNT.search(r["title"]) and not OPERATING.search(r["title"])):
            continue  # advisory / board / part-time roles: evidence only
        counted.append(r)

    spans = sorted((r["start"], r["end"]) for r in counted)
    total, cur = 0, None
    for s, e in spans:
        if cur is None or s > cur[1]:
            if cur:
                total += months_between(cur[0], cur[1])
            cur = [s, e]
        else:
            cur[1] = max(cur[1], e)
    if cur:
        total += months_between(cur[0], cur[1])
    yoe = round(total / 12, 1)

    for r in counted:
        r["level"], r["level_cue"] = role_level(r)
    long = [r for r in counted if r["months"] >= min_months and r["level"] is not None]
    recent = max(long, key=lambda r: (r["end"], r["start"])) if long else None
    level_max = max((r["level"] for r in long), default=None)
    tier = company_tier(recent["company"], strict_tier) if recent else None

    tags = {t: 0.0 for t in ALL_TAGS}
    best_team = (0, "", "")
    for r in ev_roles:
        w = 1.0 if months_between(r["end"], now) <= 96 else 0.5  # evidence older than 8 years counts half
        ctx = [(tg, note, url) for pat, tg, note, url in COMPANY_CONTEXT if re.search(pat, r["company"].lower())]
        segs = [("title", r["title"]), ("employer name", r["company"])] + list(zip(r["desc_src"], r["desc"]))
        found: dict[str, tuple[str, str]] = {}

        def hit(tag, src, phrase):
            if tag not in found or SOURCE_ORDER[src] < SOURCE_ORDER[found[tag][0]]:
                found[tag] = (src, phrase)

        for t, pat in {**TAGPAT, **SCOPE_PAT}.items():
            for src, text in segs:
                m = re.search(pat, text.lower())
                if m:
                    hit(t, src, m.group(0))
                    break
        cm = CONSULTING_FIRMS.search(r["company"])
        if cm:
            hit(CONSULTING, "employer name", r["company"])
        else:
            for src, text in segs[2:]:
                m = CONSULTING_WORK.search(text)
                if m:
                    hit(CONSULTING, src, m.group(0))
                    break
        families = []
        clean_title = STAFF_PHRASES.sub("", r["title"].lower())
        for name, rx, implied in ROLE_TEMPLATES:
            m = rx.search(clean_title)
            if m:
                families.append(name)
                for t in implied:
                    hit(t, "implied by title", f"{name} template")
        for tg, note, url in ctx:
            for t in tg:
                hit(t, "employer context", note)
        size, size_line = team_size(r["desc"])
        size_src = r["desc_src"][r["desc"].index(size_line)] if size else ""
        auto_size = size
        if size >= 2:
            hit("team_mgmt", size_src, size_line[:120])
            if size >= LARGE_TEAM:
                hit("team_large", size_src, size_line[:120])
        auto = {t: {"source": src, "phrase": phrase} for t, (src, phrase) in found.items()}
        # Your review of this role: confirmed values replace the automatic reading.
        ov = (overrides or {}).get(role_key(r)) or {}
        values = {t: 1.0 for t in found}
        if ov.get("team_size") is not None:
            size, size_src = int(ov["team_size"]), "you confirmed"
            for t, ok in (("team_mgmt", size >= 2), ("team_large", size >= LARGE_TEAM)):
                if ok:
                    found[t], values[t] = ("you confirmed", f"team of {size}"), 1.0
        for t, v in (ov.get("tags") or {}).items():
            if t not in ALL_TAGS or v is None:
                continue
            if float(v) <= 0:
                found.pop(t, None)
                values.pop(t, None)
            else:
                found[t], values[t] = ("you confirmed", "confirmed in role review"), min(1.0, float(v))
        if size >= 2 and size > best_team[0]:
            best_team = (size, _label(r), size_src)
        for t, (src, phrase) in found.items():
            evidence.append({"tag": t, "weight": w * values[t], "role": _label(r), "source": src, "phrase": phrase,
                             "url": next((u for tg, n, u in ctx if n == phrase), "")})
            tags[t] = max(tags[t], w * values[t])
        r["review"] = {"key": role_key(r), "families": families, "auto": auto, "auto_team_size": auto_size or None,
                       "final": {t: values[t] for t in found}, "team_size": size or None,
                       "reviewed": bool(ov.get("confirmed")), "recency_weight": w}

    ach = []
    for r in ev_roles:
        for d in r["desc"]:
            m = ACH_PAT.search(d)
            if m:
                ach.append({"role": f'{r["title"]} @ {r["company"]}', "line": d[:200], "match": m.group(0)})

    return {
        "YOE": min(yoe, 30.0), "YOE_raw": yoe,
        "CT": {1: 3, 2: 2, 3: 1}[tier] if tier else None, "tier": tier,
        "LV": recent["level"] if recent else None, "LV_max": level_max,
        "FN": sum(tags[t] for t in FUNC_TAGS) / len(FUNC_TAGS),
        "DM": sum(tags[t] for t in DOMAIN_TAGS) / len(DOMAIN_TAGS),
        "AC": len(ach), "tags": tags, "evidence": evidence, "achievements": ach,
        "team_size_max": {"size": best_team[0], "role": best_team[1], "source": best_team[2]} if best_team[0] else None,
        "recent_role": ({"title": recent["title"], "company": recent["company"], "start": recent["start_raw"],
                         "end": recent["end_raw"], "months": recent["months"], "level": recent["level"],
                         "level_cue": recent["level_cue"], "tier": tier} if recent else None),
        "roles": [{"title": r["title"], "company": r["company"], "start": r["start_raw"], "end": r["end_raw"],
                   "months": r["months"], "level": r.get("level"), "counted": r in counted,
                   "tier": company_tier(r["company"], strict_tier), **r["review"]} for r in ev_roles],
    }
