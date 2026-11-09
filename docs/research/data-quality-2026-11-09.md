# Data-quality research — 2026-11-09

Scope: how to get better peer, level, company-size and outcome data for the scorer (`docs/model.md` v3.7), with user-contributed CV + LinkedIn data as the long-term main source.
Labels: **V** = verified on the source page. **U** = unverified (search snippet, secondary source, or inference). No prices or numbers below are estimates; "not public" means none was found.

## What changed since last report

- First report. `docs/research/` did not exist before this run.
- Repo state read for this report:
  - Holder pool: Partnerships has 44 holders (`backend/seed/reference_partnerships_2026-10-27.json`). The other families are below 20, so they use expert-prior weights only (`v2/model.py` `hybrid_weights`).
  - LinkedIn PDF: `v2/linkedin_pdf.py` already converts "Save to PDF" text. Experience and Education are kept; other sections are dropped.
  - Hires inbox: `agents/inbox.py` rejects files that carry name, URL, photo or email fields.
  - Outcomes: there is no outcome table in `models.py`. The README lists outcome-based re-weighting as "Not yet built".

## Key findings

1. **Hourly LinkedIn reading is the largest legal/ToS risk in the pipeline.**
   - hiQ v. LinkedIn ended in a Dec 2022 consent judgment: $500k against hiQ and a permanent injunction covering both logged-in and logged-out scraping (V).
   - LinkedIn sued Proxycurl in Jan 2025. Proxycurl shut down on 4 Jul 2025 under the settlement (V).
   - LinkedIn sued ProAPIs in Oct 2025; no outcome found (V).
   - The 2024 rulings for Bright Data (Meta, X) cover logged-off scraping of public data only (V).
   - The hourly Mac task reads profiles while logged in, so it falls outside that protection.
2. **Sign In with LinkedIn (OIDC) returns identity only, not work history.**
   - Claims returned: sub, name, given/family name, picture, locale, email, email_verified (V).
   - Work history therefore has to come from the user: CV, Save-to-PDF, or the data-export archive (Positions.csv).
   - Verified on LinkedIn lists hiring and background checks as restricted uses (V), so it cannot be used for scoring.
3. **Privacy rules on automated scoring now have dates.**
   - California automated decision-making (ADMT) regulations: approved 23 Sep 2025; compliance for existing tools by 1 Jan 2027 (V).
   - Korea PIPA Art. 37-2: right to refuse fully automated decisions and to get an explanation (V).
   - EU AI Act: Annex III high-risk obligations for recruitment tools moved to 2 Dec 2027 under the Digital Omnibus political deal (V). Whether it has been published in the Official Journal is U.
   - Holders are processed without their notice. That is the weak point under GDPR Art. 14 (U) and under PIPA consent rules (U).

## Ranked options

| # | Option | Data it adds | Quality | Cost | Effort | Legal/ToS risk | Verified? | Source |
|---|---|---|---|---|---|---|---|---|
| 1 | User upload: CV + LinkedIn data archive (Positions.csv, Education.csv, Profile.csv) with consent | Dated titles, companies, education for each user; becomes a consented holder record | High: structured CSV, start/end dates | Free | Medium: CSV parser, consent flow | Low: the user's own data, with consent | Archive files V (vendor guide). LinkedIn's timing (~10 min / up to 24 h) U | [CareerBldr](https://careerbldr.gitbook.io/documentation/product-guides/importing-your-data-from-linkedin), [LinkedIn help](https://www.linkedin.com/help/linkedin/answer/50191) |
| 2 | User upload: LinkedIn Save-to-PDF (already supported) | Same fields as above, but layout-dependent | Medium: multi-column order, no official spec | Free | Low: exists in `linkedin_pdf.py` | Low | V that no official spec was found | [npm parser](https://www.npmjs.com/package/linkedin-resume-pdf-to-json) |
| 3 | Outcome capture (applied / interviewed / offer, self-reported per posting) | Labels to validate and learn weights | Medium: self-report is under-reported (Huntr says so) | Free | Medium: new table and UI | Low, with consent | V | [Huntr Q1 2026](https://huntr.co/research/job-search-trends-q1-2026) |
| 4 | SEC 10-K employee counts (Item 101(c)) via EDGAR APIs; Korea OpenDART employee report | Official headcount for public companies, to check the model-classified size bands | High, but company-wide and annual | Free | Low | None. SEC requires a User-Agent with contact details; 10 requests/s | SEC V; DART field names U | [SEC EDGAR access](https://www.sec.gov/os/accessing-edgar-data), [Harvard on 101(c)](https://corpgov.law.harvard.edu/2021/02/06/new-human-capital-disclosure-requirements), [OpenDART wrapper](https://glama.ai/mcp/servers/hypn4/opendart-fss-mcp/tools/report_employees) |
| 5 | DOL OFLC H-1B LCA and PERM disclosure files | Job titles, SOC codes and offered wages by employer; title-level cross-check for US employers | Medium: sponsored roles only | Free | Low | None (public) | FY2026 Q3 release (14 Aug 2026) V; field list U | [AILA](https://www.aila.org/library/oflc-releases-public-disclosure-data-and-selected-program-statistics-for-q3-of-fy26), [DOL OFLC](https://www.dol.gov/agencies/eta/foreign-labor/performance) |
| 6 | Ashby / Greenhouse / Lever public job APIs (already used) | Postings; Ashby `includeCompensation=true` adds structured pay ranges | High | Free | Low: add the flag in `sourcing.py` | Low. Rate limits not published; back off on 429 | Greenhouse V; Lever and Ashby V3P | [jobspipe](https://jobspipe.dev/sources/greenhouse.md), [dev.to comparison](https://dev.to/chaazee/comparing-the-job-posting-apis-of-greenhouse-lever-ashby-smartrecruiters-and-recruitee-2026-4b60) |
| 7 | People Data Labs | Person job history (`experience.start_date` YYYY-MM), `job_title_levels` (to director/vp/cxo), company size range | Medium-high. `job_company_employee_count` is a count of PDL profiles, not headcount | Free 100 credits/mo; Pro from $99/mo; title fields and data license Enterprise only | Medium | Medium: license terms not public | V | [PDL fields](https://docs.peopledatalabs.com/docs/fields), [PDL plans](https://docs.peopledatalabs.com/docs/plan-tiers) |
| 8 | Revelio Labs | 7-level seniority model, role taxonomy, company IDs resolved by entity resolution, BLS/ILO-weighted | High for aggregates | Terminal from $1,250/mo (annual); API quote-only | Medium | Medium: terms not public | V | [Revelio pricing](https://www.reveliolabs.com/pricing), [methodology](https://www.data-dictionary.reveliolabs.com/methodology.html) |
| 9 | Coresignal | Employee and company records since Jul 2016; promotion and tenure signals | Medium-high. Breaking schema change Jun 2026 | API plans $49–$5,000/mo; datasets quote-only | Medium | Medium: data is web-collected; terms not reviewed | Plans V3P; docs V | [Coresignal docs](https://docs.coresignal.com/employee-data/multi-source-employee-data), [Jun 2026 notes](https://docs.coresignal.com/release-notes/june-2026), [pricing (3rd party)](https://apiserpent.com/blog/coresignal-pricing-explained) |
| 10 | Live Data Technologies | Job-change tracking, re-validated about every 10 days (vendor claim) | Unknown | Not public | Medium | Unknown | U (competitor page only) | [Signalbase](https://www.trysignalbase.com/best-job-change-tracking-tools) |
| 11 | Crunchbase | Funding, company firmographics | Medium | Pro $49–99/mo has no API; API is quote-only; free API ended 2025 | Low | Medium: Applications license needs attribution | V3P | [ZoomInfo on Crunchbase](https://pipeline.zoominfo.com/sales/crunchbase-api) |
| 12 | Apollo | Contacts, titles | Medium | $49–$119 per user per month | Low | High: terms limit use to internal purposes, ban use in your own product without authorization, ban competing | Terms V | [Apollo API terms](https://www.apollo.io/terms/api) |
| 13 | Levels.fyi ladders (used as an input to `agents/level.py`) | Level ladders, pay | High | API on request; price not public | Low | High without a signed agreement: terms ban scraping, compiling datasets and AI use | V | [Levels.fyi terms](https://levels.fyi/about/terms.html), [API access](https://levels.fyi/api-access) |
| 14 | Pave / Carta benchmarks | Pay by level; Carta maps titles to levels with an LLM | High | Pave "Lite" free; Pro paid | Low | Low (read published methods only) | V | [Pave](https://pave.com/products/market-data-launch), [Carta](https://carta.com/blog/compensation-bands/) |
| 15 | Singapore MOM occupational wages 2025 | Medians for 500+ occupations | Medium: residents only, mostly medians | Free | Low | None | V | [MOM](https://stats.mom.gov.sg/Pages/Occupational-Wages-Tables2025.aspx) |
| — | Continue logged-in LinkedIn reading (hourly Mac task) | Holder profiles | High | Free | Exists | **High**: User Agreement §8.2 bans automated collection (U, verbatim not read); API Terms §3.1(24) ban scraping outside the APIs (V); hiQ injunction and Proxycurl precedents (V) | V/U as noted | [LinkedIn API terms](https://developer.linkedin.com/legal), [hiQ settlement](https://newmedialaw.proskauer.com/2022/12/08/hiq-and-linkedin-reach-proposed-settlement-in-landmark-scraping-case/), [Proxycurl](https://nubela.co/blog/goodbye-proxycurl/) |
| — | Proxycurl | — | — | — | — | Shut down 4 Jul 2025 | V | [Nubela](https://nubela.co/blog/goodbye-proxycurl/) |

## Recommended next steps (report only; no code changed)

1. **Outcome table and capture.**
   - Where: new `Outcome` model in `backend/app/models.py` (user, posting, stage, date, score snapshot ID, `MODEL_VERSION`); stage buttons on postings in `routers/matches.py`; read by `v2/market.py` to re-estimate weights.
   - Measure:
     - outcomes per week;
     - share of top-10 matches with any outcome;
     - once 30+ interviews exist, NDCG@10 and calibration of interview vs. score decile ([NDCG](https://dblp.uni-trier.de/rec/html/journals/tois/JarvelinK02), [calibration](https://ar5iv.arxiv.org/html/1706.04599)).
   - Keep the logistic switch at 100+ outcomes, per the model rule.
2. **LinkedIn data-archive import, with consent, as a holder source.**
   - Where: new `v2/linkedin_export.py` next to `linkedin_pdf.py`. Parse Positions.csv and Education.csv into the same role structure as `reader.parse_linkedin`.
   - Add an opt-in "contribute my anonymized record to the peer pool" that writes through the same derive-and-discard path as `agents/inbox.derive`.
   - Measure:
     - parse agreement between archive and PDF on the same user (roles, dates, titles);
     - share of the pool from consented uploads vs. the Mac task;
     - families reaching 20 holders.
3. **Headcount check for size bands.**
   - Where: `agents/company_facts.py` and `v2/industry.py`. For public companies, compare the model-classified band (`CompanySector`) with the 10-K employee count (EDGAR) or the DART employee report.
   - Measure: band agreement rate, and how many effective-level (LV) values change when a band is corrected.

## User-upload design

- **Consent** (PIPA needs separate consent per purpose; V [BKL](https://www.bkl.co.kr/en/law/insight/newsletter/5374)). Three separate, unticked boxes:
  1. Score my CV (required for the service).
  2. Add my de-identified record to the peer pool.
  3. Use my outcomes to tune weights.
  - Each can be withdrawn on its own.
  - The notice must also explain the score logic and the right to human review or to refuse automated scoring: CCPA ADMT (V [White & Case](https://www.whitecase.com/insight-alert/cppa-finalizes-rules-admt-risk-assessments-and-cybersecurity-audits-requirements)), PIPA Art. 37-2 (V [Prighter](https://prighter.com/resources/laws/korean-pipa/main/articles/article-37-2)), GDPR Art. 22 (V [text](https://www.privacy-regulation.eu/en/22.htm)).
- **Accepted inputs:**
  - CV (PDF/DOCX);
  - LinkedIn Save-to-PDF;
  - LinkedIn data archive, larger-archive ZIP (only Positions, Education, Profile headline and Skills are read; the rest of the ZIP is discarded unopened).
  - OIDC sign-in is optional and used for login plus `email_verified` only.
- **Kept for the user's own scorecard:** parsed roles (title, company, dates, location), degrees, and the user's own CV text, deletable at any time.
- **Kept for the pool** (same rule as holders today): derived factors and the anonymized role list only (tier, level band, months, industry, region, function tags).
  - Coarsen hire date to quarter.
  - Hold back company plus exact title when fewer than k pool rows share them.
- **Discarded:** name, photo, URLs, email, phone, connections, messages, endorsements, recommendations, free-text descriptions after tagging. Reuse the `inbox.FORBIDDEN` field screen.
- **De-identification:**
  - Seed reference rows today carry `company` and current `title`. With a hire window, that can identify one person. Add a minimum cell size before display: LinkedIn Salary tested thresholds of 3–10 and used hierarchical smoothing instead of differential privacy (V [paper](https://ar5iv.arxiv.org/html/1705.06976)).
  - Display "nearest role holders" by tier and band, not by company, when the cell is under k.
  - The PDPC expects "no serious possibility" of re-identification for anonymized data (V [PDPC guidelines](https://www.pdpc.gov.sg/-/media/files/pdpc/pdf-files/advisory-guidelines/advisory-guidelines-on-the-use-of-personal-data-in-ai-recommendation-and-decision-systems.pdf)).
- **Deletion:**
  - On request or account closure: delete raw uploads and the profile immediately, remove the user's pool row, and re-run the affected family snapshot.
  - Uploaded files: retain raw only until the parse is reviewed, then delete.
  - Outcomes: keep only as long as consent 3 stands.
- **Incentives** (U, design proposal, not sourced): the full scorecard and gap plan need an upload; peer comparison unlocks once the user contributes; show the user how their family's sample size grows.
- **Fake/inflated profiles:**
  - Check dates (overlaps, future dates, implausible jumps of 2+ bands at the same company).
  - Check the company against the `CompanySector` headcount band (a VP title at a company under 50 people is already read down in §2a).
  - Hold a contributed record out of the pool until its family has an independent source. A work-email domain check is optional (U).
  - Platform scale: LinkedIn restricted 24.4M accounts proactively in Jul–Dec 2025 (V [transparency report](https://about.linkedin.com/transparency/community-report)).

## Utilization notes

- **Entity resolution:** use Splink (Fellegi-Sunter, open source; V [gov.uk](https://www.gov.uk/government/publications/joined-up-data-in-government-the-future-of-data-linking-methods/splink-mojs-open-source-library-for-probabilistic-record-linkage-at-scale)) to dedupe holders across Mac reads, trade-press moves and user uploads. Match on company, title, start month and prior employer, without names.
- **Title to level:**
  - Keep the §2a size rule.
  - Cross-check against PDL `job_title_levels` or Revelio's 7-level model if licensed.
  - O\*NET Job Zones measure preparation, not corporate rank, so they do not separate Director from VP (V [O\*NET](https://onetcenter.org/whatsnew.html)).
- **Sample size:**
  - A nonparametric 95% interval needs n ≥ 39; n ≥ 119 for a 90% CI on it (V [analyse-it](https://analyse-it.com/docs/user-guide/referenceinterval/quantile)).
  - The current gates (10 for a scorecard, 20 for a factor) are below that, so show a bootstrap range on the score (`n_boot` already exists).
- **Cold start:** shrink small families toward their parent (role cluster → sector), as LinkedIn Salary did (V). This is consistent with the existing prior blend `(50·prior + n·market)/(50+n)`.
- **Label quality:**
  - Keep the 3-read majority in the reader and the golden cases (`seed/golden_reader.json`).
  - Add the archive-vs-PDF agreement check (step 2) as a second golden set.

## Open questions / unverified

- Verbatim LinkedIn User Agreement §8.2 text (page not readable this run).
- LinkedIn's official archive turnaround times.
- Whether the Member Data Portability API is EEA-only and which domains it returns beyond PROFILE.
- Whether the EU Digital Omnibus has been published in the Official Journal.
- Exact effective dates for the PIPA 2023 amendment.
- Field names in the OFLC FY2026 files and the OpenDART employee report.
- License terms for display or derivative use: PDL, Revelio, Coresignal, Live Data.
- Whether k-anonymity on the pool (company + title + quarter) leaves enough cells to keep the "nearest holders" view useful. Measure once k is chosen.

## Sources

- [LinkedIn OIDC sign-in](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2)
- [Verified on LinkedIn overview](https://learn.microsoft.com/en-ca/linkedin/consumer/integrations/verified-on-linkedin/overview)
- [LinkedIn news: Verified on LinkedIn](https://news.linkedin.com/2025/Verified_on_LinkedIn)
- [LinkedIn Member Data Portability API](https://learn.microsoft.com/en-us/linkedin/dma/member-data-portability/shared/member-snapshot-api)
- [LinkedIn help: data export](https://www.linkedin.com/help/linkedin/answer/50191)
- [CareerBldr LinkedIn import](https://careerbldr.gitbook.io/documentation/product-guides/importing-your-data-from-linkedin)
- [Takeout Day LinkedIn guide](https://takeoutday.org/guides/how-to-export-linkedin-data)
- [linkedin-resume-pdf-to-json](https://www.npmjs.com/package/linkedin-resume-pdf-to-json)
- [Resume parsing benchmark (arXiv 2510.09722)](https://arxiv.org/pdf/2510.09722v1)
- [LinkedIn community report](https://about.linkedin.com/transparency/community-report)
- [Huntr Q1 2026](https://huntr.co/research/job-search-trends-q1-2026)
- [LinkedIn API Terms](https://developer.linkedin.com/legal)
- [Unipile on LinkedIn scraping](https://www.unipile.com/is-linkedin-scraping-legal/)
- [hiQ v. LinkedIn settlement](https://newmedialaw.proskauer.com/2022/12/08/hiq-and-linkedin-reach-proposed-settlement-in-landmark-scraping-case/)
- [Meta v. Bright Data](https://www.fbm.com/data-analytics/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/)
- [Meta drops Bright Data suit](https://techcrunch.com/2024/02/26/meta-drops-lawsuit-against-web-scraping-firm-bright-data-that-sold-millions-of-instagram-records/)
- [X Corp v. Bright Data](https://natlawreview.com/article/x-corp-loses-battle-over-public-data-access)
- [LinkedIn v. ProAPIs](https://securityaffairs.com/183001/security/linkedin-sues-proapis-for-15k-month-linkedin-data-scraping-scheme.html)
- [Proxycurl shutdown](https://nubela.co/blog/goodbye-proxycurl/)
- [GDPR Art. 22](https://www.privacy-regulation.eu/en/22.htm)
- [CCPA employee exemption expiry](https://hklaw.com/en/insights/publications/2022/12/california-employee-data-exemption-expires-on-january-1)
- [CPPA ADMT rules](https://www.whitecase.com/insight-alert/cppa-finalizes-rules-admt-risk-assessments-and-cybersecurity-audits-requirements)
- [Korea PIPA 2023 amendment (BKL)](https://www.bkl.co.kr/en/law/insight/newsletter/5374)
- [PIPA Art. 37-2](https://prighter.com/resources/laws/korean-pipa/main/articles/article-37-2)
- [PDPC AI advisory guidelines](https://www.pdpc.gov.sg/-/media/files/pdpc/pdf-files/advisory-guidelines/advisory-guidelines-on-the-use-of-personal-data-in-ai-recommendation-and-decision-systems.pdf)
- [EU AI Act omnibus (Gibson Dunn)](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/)
- [PDL fields](https://docs.peopledatalabs.com/docs/fields)
- [PDL plan tiers](https://docs.peopledatalabs.com/docs/plan-tiers)
- [PDL job title class](https://docs.peopledatalabs.com/docs/job-title-class)
- [Coresignal employee data](https://docs.coresignal.com/employee-data/multi-source-employee-data)
- [Coresignal Jun 2026 release notes](https://docs.coresignal.com/release-notes/june-2026)
- [Coresignal pricing (3rd party)](https://apiserpent.com/blog/coresignal-pricing-explained)
- [Revelio pricing](https://www.reveliolabs.com/pricing)
- [Revelio methodology](https://www.data-dictionary.reveliolabs.com/methodology.html)
- [Revelio acquires Salary Board](https://www.prnewswire.com/news-releases/revelio-labs-acquires-salary-board-to-expand-global-compensation-analytics-302444250.html)
- [Live Data (3rd party)](https://www.trysignalbase.com/best-job-change-tracking-tools)
- [Crunchbase API (3rd party)](https://pipeline.zoominfo.com/sales/crunchbase-api)
- [Crunchbase free tier ended (3rd party)](https://dev.to/agenthustler/crunchbase-api-in-2026-free-tier-gone-what-startup-data-hunters-do-now-1177)
- [Apollo pricing (3rd party)](https://docket.io/resources/research/apollo-pricing)
- [Apollo API terms](https://www.apollo.io/terms/api)
- [LinkedIn vs Apollo/Seamless (3rd party)](https://www.leadgenius.com/resources/linkedins-crackdown-on-data-scrapers-why-apollo-io-and-seamless-ai-were-targeted--and-whos-next)
- [SEC EDGAR access](https://www.sec.gov/os/accessing-edgar-data)
- [Item 101(c) human capital](https://corpgov.law.harvard.edu/2021/02/06/new-human-capital-disclosure-requirements)
- [OFLC FY26 Q3 release (AILA)](https://www.aila.org/library/oflc-releases-public-disclosure-data-and-selected-program-statistics-for-q3-of-fy26)
- [DOL OFLC performance data](https://www.dol.gov/agencies/eta/foreign-labor/performance)
- [Levels.fyi API access](https://levels.fyi/api-access)
- [Levels.fyi terms](https://levels.fyi/about/terms.html)
- [Pave market data](https://pave.com/products/market-data-launch)
- [Carta compensation bands](https://carta.com/blog/compensation-bands/)
- [Greenhouse board API (jobspipe)](https://jobspipe.dev/sources/greenhouse.md)
- [Job-board API comparison](https://dev.to/chaazee/comparing-the-job-posting-apis-of-greenhouse-lever-ashby-smartrecruiters-and-recruitee-2026-4b60)
- [OpenDART employee report (wrapper)](https://glama.ai/mcp/servers/hypn4/opendart-fss-mcp/tools/report_employees)
- [OpenDART employee info (wrapper)](https://glama.ai/mcp/servers/ChangooLee/mcp-opendart/tools/get_employee_info)
- [Singapore MOM wages 2025](https://stats.mom.gov.sg/Pages/Occupational-Wages-Tables2025.aspx)
- [Splink (gov.uk)](https://www.gov.uk/government/publications/joined-up-data-in-government-the-future-of-data-linking-methods/splink-mojs-open-source-library-for-probabilistic-record-linkage-at-scale)
- [O*NET what's new](https://onetcenter.org/whatsnew.html)
- [Quantile sample size (analyse-it)](https://analyse-it.com/docs/user-guide/referenceinterval/quantile)
- [LinkedIn Salary paper](https://ar5iv.arxiv.org/html/1705.06976)
- [PriPeARL](https://arxiv.org/abs/1809.07754)
- [BLS OEWS presentation](https://www.bls.gov/opub/hom/oews/presentation.htm)
- [Census DP overview](https://www.ctdata.org/blog/an-overview-of-differential-privacy-in-the-2020-decennial-census)
- [NDCG (Järvelin & Kekäläinen)](https://dblp.uni-trier.de/rec/html/journals/tois/JarvelinK02)
- [Calibration (Guo et al.)](https://ar5iv.arxiv.org/html/1706.04599)
