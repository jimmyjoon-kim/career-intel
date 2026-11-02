# Career Intel scoring model (v3.2, 2026-11-02)

What the score is: where your record sits among people who currently hold a role family (Partnerships, Ad Sales,
GM / Regional lead, BD / Alliances, Growth, or any role you add), on factors that can be read from a CV or a LinkedIn
profile. It is not a hiring probability and it does not measure interviews, references, reputation or network.

## 1. Peer group
- Role holders collected from public profiles (read-only) and press, stored as derived values only (no names, links,
  photos or text). Screened on arrival: no personal fields, dated roles required, no duplicates.
- Each holder is read **as of the date they were hired**: every role at their current employer is excluded and
  recency is measured from the hire date. (Reads before 2026-11-02 included the current seat; they are replaced once
  20 corrected reads exist for a family.)
- An anonymized role list (tier, level band, months, industry, region, function tags; no company names) is kept so
  factors can be recomputed when the model changes.

## 2. Factors (same rules for you and every holder)
| Factor | Value | Cap |
|---|---|---|
| YOE years of experience | months in counted roles / 12 | holders' 75th percentile |
| LV level held | band of most recent 12+ month role (0 IC … 5 C-level); one band lower if VP+ at a Tier 3 employer | 75th pct |
| FN function evidence | share of the family's function signals shown (Partnerships: partnerships, BD, channel; BD: BD, partnerships; Ad Sales: sales leadership, ad sales; GM: P&L, team leadership, large team; Growth: growth) | 75th pct |
| FT same function at a major company | 2 = Tier 1 employer, 1 = Tier 2, role of 12+ months in this function (GM: VP/GM band) | none |
| DM domain breadth | share of ad tech, AI, mobile, SaaS domains evidenced | 75th pct |
| CT employer tier & journey | best role in 10 years: Tier 1 = 3, Tier 2 = 2, Tier 3 = 1; +1 IPO/acquisition held through | none |
| PD hired into major companies | distinct Tier 1/2 employers (12+ months, 20 years), Tier 1 counted double; merger moves excluded | none |
| US US market experience | months in US-located roles, up to 60 | 60 |
| UQ scarce experience | rarity-weighted hyperscaler, government, consulting, 0-to-1, mobile | 75th pct |
| AC quantified outcomes | count of quantified achievement lines | 75th pct |
| AI current AI relevance | 0.6 × AI work (recency-weighted) + 0.4 × completed AI degree | 75th pct |
| TK technical depth | mean of technical degree, technical role, technical product work | 75th pct |
| ED degree level | highest completed degree | none |
| SCH school tier | QS top 30 = 2, 31–100 = 1, else 0 (QS 2027 via secondary source) | none |
| FLD degree field | engineering/CS/science = 1, economics/business = 0.5, other = 0 | none |

Caps: credit stops at what the strongest quarter of holders show. Without them a long, broad career outranks every
holder by being "more" on each factor, while real holders are strong on a few.

A factor read only from newer peer files (PD, SCH, FLD, US, FT) counts once 20 holders in the group have it.

## 3. Formula
For each factor k: your percentile p_k among the holders (ties count half), after caps.
Score = Σ w_k · p_k / Σ w_k over the factors that count. 50 = the median holder on every factor.

Weights w_k = blend of an expert prior and measured market discrimination:
w_k = (50 · prior_k + n · market_k) / (50 + n), n = holders in the group.

Prior (sums to 112, normalized): FN 16, LV 15, FT 12, YOE 10, US 10, CT 8, DM 8, PD 8, AI 6, UQ 5, AC 4, ED 3, TK 3,
SCH 2, FLD 2. Basis:
- Recruiters rate years (84%) and type of experience (83%) above education level (35%) at screening
  (SHRM, 2022, n = 1,030+). https://www.shrm.org/topics-tools/news/talent-acquisition/recruiters-say-experience-top-factor-applicant-evaluation
- Google Director commercial postings set 15 years as a floor (three postings read 2026-11-02); no source shows
  value beyond it, hence the cap.
- School-rank pay effect fades from about 12% at year 1 to about 1.4% (n.s.) at year 10 (Weinstein, IZA DP 10911).
  https://repec.iza.org/dp10911.pdf
- US experience earns larger returns than foreign experience (US immigrant men; direction only).
  https://econpapers.repec.org/paper/arxpapers/2512.18827.htm
- AI labs' commercial hires come from the same function at big tech: OpenAI ads mostly from Meta ads; Anthropic
  go-to-market from Salesforce, Google, AWS, Databricks (secondary reports, no shares).
  https://dealroom.co/news/163471-openais-ad-run-rate-hits-1b-as-it-poaches-meta-talent-chases-2-4b-target/
  https://www.salesforceben.com/why-anthropic-is-raiding-salesforce-for-sales-talent/

## 4. What it does not know
US network, size and scope of each business run, how competitive each hire was, reputation, interview performance,
and hiring outcomes. Weights are not yet validated against who gets interviews and offers; recording outcomes is the
step that would make them so.
