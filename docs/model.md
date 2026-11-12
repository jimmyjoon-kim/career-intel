# Career Intel scoring model (v3.8, 2026-11-12)

## 0. Scoring guideline (council review, 2026-11-12)
1. The score measures how your record compares with role holders' records when they were hired. It is not hiring
   competitiveness: nobody in the comparison was rejected. Wording in the app must not claim more.
2. One rule for everyone: every factor is read and scored the same way for you and for holders, in every path
   (score, range, what-ifs, posting view). A factor that is unknown for a person takes the neutral value 50.
3. The top tier is defined by an outcome outside the score (holders hired into Tier 1 employers; Tier 1 or 2 if fewer
   than 5; not shown under 5), never by the score itself.
4. A factor with no published evidence and no measured outcome weight is shown as information, not scored (school
   tier, degree field). One underlying fact is not counted more than once at full weight (employer tier).
5. Nothing falls back to another role's rules: a role without its own function signals has no function factor.
6. Evidence is read from sentences about work done, not from keyword or skills lists.
7. Every rank carries its group size; under 20 holders it is provisional. Times to close are judgments and are
   labeled so; structural gaps are shown apart from capability gaps.
8. A change that moves a score by more than 3 points ships with a before-and-after table and the reason.

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
| LV effective level | band of most recent 12+ month role (0 IC … 5 C-level), adjusted by the employer's headcount (section 2a) | 75th pct |
| FN function evidence | share of the family's function signals shown (Partnerships: partnerships, BD, channel; BD: BD, partnerships; Ad Sales: sales leadership, ad sales; GM: P&L, team leadership, large team; Growth: growth) | 75th pct |
| FT same function at a major company | 2 = Tier 1 employer, 1 = Tier 2, role of 12+ months in this function (GM: VP/GM band) | none |
| DM domain fit | domains evidenced, weighted by how many holders of this role show each domain (fit, not breadth) | 75th pct |
| CT employer tier | best 12+ month role in the last 10 years: Tier 1 = 3, Tier 2 = 2, Tier 3 = 1 | none |
| PD hired into major companies | distinct Tier 1/2 employers (12+ months, 20 years), Tier 1 counted double; merger moves excluded | none |
| US market experience | months in roles located in your target market (first target location), up to 60; not scored without a target market | 60 |
| UQ scarce experience | rarity-weighted hyperscaler, government, consulting, 0-to-1, mobile | 75th pct |
| AC quantified outcomes | count of quantified achievement lines | 75th pct |
| AI current AI relevance | 0.6 × AI work (recency-weighted) + 0.4 × completed AI degree (in progress = 0, for you and holders) | 75th pct |
| TK technical depth | mean of technical degree, technical role, technical product work | 75th pct |
| ED degree level | highest completed degree | none |
| SCH school tier (information only, not scored) | QS top 30 = 2, 31–100 = 1, else 0 (QS 2027 via secondary source) | none |
| FLD degree field (information only, not scored) | engineering/CS/science = 1, economics/business = 0.5, other = 0 | none |
| SG ad tech sides (ad families only) | sides shown in the last 10 years: demand (advertisers, agencies, brands, UA / DSP) and supply (publishers, app monetization, SSP / mediation); both = 2 (unified) | none |

### 2a. Effective level (titles compared by scope)
Large employers (5,000+ employees, or Tier 1/2 when headcount is unknown) are the reference scale. Smaller employers'
titles are read down: 500–4,999 employees: VP and above −1; 50–499: Director/Head −1, VP and above −2; under 50:
Director/Head −1, VP −2, SVP and C-level −3, and never above Director (a C-level title at a 5-person startup reads as Director).
Headcount bands are classified once per company by a model and stored ('unknown' if it does not know the company;
then Tier 3 is read as 50–499). Same rule for you and every holder.
Basis: Pave — about half of Directors at companies under ~500–1,000 employees do not manage managers; executive orgs
at companies under 100 people span ~15–50 people vs ~36 total reports for a Director at 3,000+ (https://pave.com/blog-posts/what-the-heck-is-head-of,
https://www.pave.com/blog-posts/average-team-size-benchmarks-for-managers-executives); Mercer IPE scales job size by
organization size (https://www.mercer.com/en-us/solutions/talent-and-rewards/job-architecture/job-evaluation-ipe);
startup-to-big-tech moves are typically 1–2 levels down (anecdotal, unverified). No validated cross-size mapping for
commercial roles was found; the step sizes are a judgment.

Titles also read one band lower when interim, acting or fractional, and when a VP+ title has single-country scope.
Employers under 50 people cap effective level at Director (band 1); 50–499 at Head / Senior Director (band 2).

Caps: credit stops at what the strongest quarter of holders show. Without them a long, broad career outranks every
holder by being "more" on each factor, while real holders are strong on a few.

Capped values get exactly the cap percentile (no extra credit above the strongest quarter).

A factor read only from newer peer files (PD, SCH, FLD, US, FT, SG) counts once 20 holders in the group have it (in a
group of 10–19 holders: once 80% have it). Groups of 10–19 holders get a scorecard with a plain note on the count.

## 3. Formula
For each factor k: your percentile p_k among the holders (ties count half), after caps.
Score = Σ w_k · p_k / Σ w_k over the factors that count; an unknown factor takes 50. Your position among holders' scores
(not the score itself) says where you sit: the median holder is at position 50.

Flags, not caps (v3.6, 2026-11-03): when 60%+ of holders show US market experience, same function at a major
company, function evidence or domain fit, and you show none, it is reported as a flag; the factor counts at its weight.
A cutoff set by what most holders happen to have is normative, not a stated job requirement: selection guidance ties
cutoffs to what the job requires (Uniform Guidelines, 41 CFR 60-3.5, https://www.law.cornell.edu/cfr/text/41/60-3.5;
Cascio & Aguinis 2001, https://www.hermanaguinis.com/pdf/RPPA2001.pdf). Foreign experience is discounted on average
(Oreopoulos field experiment, https://nber.org/digest/sep09/w15036.html; Fortin, Lemieux & Torres 2016), but no source
gives a size for Director/VP commercial hires or supports a cap. A posting that states a US-market requirement scores
it as an unmet requirement in job fit. (v3.4–3.5 capped the score at the median holder's.) Only leader seats
(Director/Head and above) are compared once 10+ remain.

Top tier (v3.8): holders hired into Tier 1 employers (Tier 1 or 2 if fewer than 5; not shown under 5). Each factor shows
your gap to the top tier's median percentile, or to the median holder when no top tier is shown. Signals listed are
those 60%+ of the top tier show and 20+ points more often than the rest: a description, not a cause.

SG (ad tech sides) is weighted 8 for Ad Sales, Partnerships, BD / Alliances and GM; 0 elsewhere. It counts only for
holders read with the demand-side signal (tag version 2, from 2026-11-02). Postings get seg_demand_side /
seg_supply_side tags (both = a unified role), so job fit shows which side a role sells.

Weights w_k = blend of an expert prior and measured market discrimination:
w_k = (50 · prior_k + n · market_k) / (50 + n), n = holders in the group.

Prior (v3.8, normalized): FN 16, LV 15, YOE 10, DM 9, FT 9, US 8, AI 6, CT 3, UQ 3, ED 3, TK 3, PD 2, AC 2, SCH 0, FLD 0
(+ SG 8 in ad families). Employer tier (CT + PD + FT) totals 14, down from 24. Measured market weights are used for
Partnerships only (other groups too small). Basis:
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

## 3a. Market fit (v3.7): experience in the job's market, multi-region scope
Applies only to the market a job is based in (US jobs: US experience; APAC jobs: APAC experience; EMEA likewise).
- Job market: region in the title ("Head of APAC"), else the location's region; "global" titles carry no market.
- Effective months E = months located there + 0.5 x months covering it from elsewhere (or global scope) + 0.25 x months
  at an employer headquartered there; a different country in the same region counts half (APAC / EMEA); cap 60.
- Job fit for a job in that market: fit x (1 - 0.15 x (1 - min(E, 36) / 36)): at most 15% off with no experience
  there, gone at 36 effective months; 7.5% for multi-region roles. Where the posting states a US-market requirement,
  that requirement is scored from E (full at 24 months) instead, so it is not counted twice.
- Multi-region roles (global title or a stated multi-region scope): + up to 5 points for months in multi-region roles
  (full at 36).
- Peer score: the market factor measures months in roles located in your target market (first target location), for
  you and every holder; without a target market it is not scored. Holders' seat location is recorded from 2026-11-03 so
  the factor can later compare with holders based in that market.
- Work authorization stays a separate pass/fail screen; it never enters these numbers.
- Basis: local experience raises callbacks (Oreopoulos field experiment, https://nber.org/digest/sep09/w15036.html),
  the gap is smaller at large employers and shrinks over time; returns to foreign experience are higher from
  high-income countries (https://www.nber.org/system/files/working_papers/w21914/w21914.pdf); international stints
  carry a CEO pay premium (ESCP, 275 CEOs). No source sizes the effect for Director/VP commercial hires: 15%, 36, 24 and
  5 are judgments, to be re-estimated from recorded outcomes (Bayesian while few; logistic at 100+ outcomes).

## 3b. Known limits kept open (council review)
- Holders are read from LinkedIn text; you are read from CV plus LinkedIn. Text-read factors (function, domain,
  scarce experience, quantified lines) grow with the amount of text; caps bound this, they do not remove it.
- Buzzwords written into full sentences still raise text-read factors. Weighting evidence by role months is the fix.
- Title templates (a CEO or GM title implies P&L and people management) apply at any employer size.
- Employer tiers come from a hand-written list that leans toward ad tech and AI; it is static, not by date.
- Job-fit requirement weights come from posting frequency only; they are not yet checked against hire profiles.
- The position range holds caps and weights fixed, so it is somewhat too narrow.

## 3c. Validation run against an outside outcome (2026-11-12, n = 99 holders read at hire)
Question: do the factors separate holders hired into Tier 1 employers (30) from the other holders in the same role?
Method: within-family percentiles, within-family AUC, permutation test shuffling the outcome inside each family;
ridge logistic with leave-one-out. Result:
- The composite does not separate them: AUC 0.37 for Tier 1 (p = 0.08), 0.50 for Tier 1 or 2 (p = 1.0). 0.5 = chance.
- No single factor passes a correction for 15 factors tested (threshold p < 0.003). Nominal signals only: prior
  employer tier and prior major-company hires for Tier 1 or 2 (AUC 0.65, p = 0.02); fewer target-market months among
  Tier 1 hires (AUC 0.35, p = 0.01), which is probably a sampling effect (Tier 1 holders were collected from more
  regions; seat region is recorded only from 2026-11-03).
- Fitted weights are not used: the leave-one-out model reaches AUC 0.63 only with mostly negative coefficients.
Why it cannot work yet: every holder was hired into a leader seat, so this compares winners with winners; peers come
from search, not a random sample; 30 positives is too few. Weights stay the expert prior, labeled unvalidated. What
would validate them: recorded outcomes (applied, interview, offer) from users, or a comparison group of people one
level below the role.

## 4. What it does not know
US network, size and scope of each business run, how competitive each hire was, reputation, interview performance,
and hiring outcomes. Weights are not yet validated against who gets interviews and offers; recording outcomes is the
step that would make them so.
