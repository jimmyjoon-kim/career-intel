"""LinkedIn "Save to PDF" text -> the on-screen Experience layout the reader parses.

The PDF lists each company first (Company, optional total duration, then Title / dates / location per role), while the
Experience page lists Title then Company. This rewrites each role as:
    Title
    Company · Full-time
    Mon YYYY - Mon YYYY · duration
    location / description lines
The result is shown to the user for review before it replaces anything."""

from __future__ import annotations

import re

_M = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
PDF_DATE = re.compile(rf"^((?:{_M} )?\d{{4}})\s*[-–]\s*((?:{_M} )?\d{{4}}|Present)\s*(?:\((.*)\))?$")
DURATION = re.compile(r"^\d+ (?:years?|months?)(?: \d+ months?)?$")
NOISE = re.compile(r"^(Page \d+ of \d+|Contact|Top Skills|Languages|Certifications|Honors-Awards|Publications|Summary)$")
LOCATION = re.compile(r"(,\s*[A-Z][A-Za-z .]+$)|\bArea$|\bRegion$|^(Remote|Hybrid|On-site)$")
SECTION_END = re.compile(r"^(Education|Licenses|Volunteer|Skills)\b")


def _sentence(s: str) -> bool:
    return s.endswith((".", ";", ":")) or len(s.split()) > 9 or s.startswith(("•", "-", "*", "·"))


def _section(text: str) -> tuple[str, str]:
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and not NOISE.match(ln)]
    try:
        start = next(i for i, ln in enumerate(lines) if ln == "Experience")
    except StopIteration:
        start = -1
    exp, edu, cur = [], [], None
    for ln in lines[start + 1:]:
        if ln == "Education":
            cur = edu
            continue
        if cur is edu:
            edu.append(ln)
        elif SECTION_END.match(ln) and exp:
            cur = []  # ignore other trailing sections
        elif cur is None:
            exp.append(ln)
    return "\n".join(exp), "\n".join(edu)


def convert(text: str) -> dict:
    exp, edu = _section(text)
    L = exp.split("\n") if exp else []
    dates = [i for i, ln in enumerate(L) if PDF_DATE.match(ln) and i >= 1]
    heads, group = [], None
    for n, i in enumerate(dates):
        prev2 = L[i - 2] if i >= 2 else ""
        prev_date = dates[n - 1] if n else -1
        if prev2 and DURATION.match(prev2) and i >= 3 and i - 3 > prev_date:
            company = group = L[i - 3]          # company with several roles
            tstart = i - 3
        elif group and (i - 2 <= prev_date + 1 or not prev2 or _sentence(prev2) or LOCATION.search(prev2) or PDF_DATE.match(prev2)):
            company, tstart = group, i - 1      # next role at the same company
        elif prev2 and i - 2 > prev_date:
            company, group, tstart = prev2, None, i - 2  # a single-role company
        else:
            company, tstart = "", i - 1
        heads.append((i, L[i - 1], company, tstart))
    out = []
    for n, (i, title, company, _) in enumerate(heads):
        m = PDF_DATE.match(L[i])
        dur = f" · {m.group(3)}" if m.group(3) else ""
        out += [title] + ([f"{company} · Full-time"] if company else []) + [f"{m.group(1)} - {m.group(2)}{dur}"]
        stop = heads[n + 1][3] if n + 1 < len(heads) else len(L)
        out += L[i + 1:stop] + [""]
    return {"experience_text": ("Experience\n" + "\n".join(out)).strip() if heads else "",
            "education_text": edu, "roles": len(heads)}
