# Plan: peer data and job-based scoring (council review, 2026-11-13)
Three independent reviews (peer pipeline, job discovery and fit, outside methods), reconciled. Facts carry their source
in the reviews; parameters without a source are judgments and are labeled.

## Done 2026-11-13
- Collection reopens until each role has 30 holders read at hire; request file rewritten every run; full groups are
  topped up with 5 recent hires a month (was 30). Switch: PEER_COLLECTION (currently false on the server).
- Seed reload no longer deletes collected holders. A bad holder entry no longer discards its file. Skip reasons counted.
- Lead-level seats are left out of leader groups (the old filter never removed anything).
- Your stated lowest level and "no single-country roles" are strict screens (were soft; such postings resurfaced).
- Web-found postings: matched to board jobs by job id; marked stale after 30 days unconfirmed. Board closing scoped to
  the company. Level assessment kept across re-reads. Group concentration note (5+ employers, none above 25%).

## A. Peer data
1. Cohort, not family (next). Weight each holder by: hire recency (1.0 within 5 years, 0.5 at 5-10, 0.2 older), seat
   level vs your target band (1.0 same, 0.5 one away, 0 beyond), seat region vs your target market (1.0 / 0.5), and an
   employer cap (1 / max(1, n_employer / 3)). Effective n = (sum w)^2 / sum w^2; under 20 = provisional. Widen in order:
   recency, region, level, sibling family. Show the cohort line with what was widened. Weights are judgments.
   Fields to add per holder: seat level, seat tier, seat size, seat sector, seat scope (seat region exists).
2. Display rule (next): a rank needs 5+ employers and none above 25% (Aon Radford policy); always with its interval.
   Under 20 holders, pool the family 50/50 with all holders (empirical-Bayes style shrinkage; the 50/50 is a judgment).
3. Sampling quotas per role of 30 (next): 20+ hired in the last 36 months; Director/Head 18, VP 9, SVP+ 3; Tier 1/2/3
   10 each; half in users' target markets, 5 minimum per other region; 3 per employer at most. Request file carries
   the open strata; the reader reports how many candidates it saw per stratum.
4. Comparison group (next): (a) free: each holder's earlier hires, read as of each hire, labeled survivor-biased;
   (b) 10 people one level below per role (60 reads). Validation then tests at most 3 factors named in advance
   (30 positives supports about 3 by the events-per-variable rule).
5. Recompute without re-reading (next): store per role a set of cue ids from a fixed lexicon (no proper nouns) so new
   tags can be derived later. Today new tags never reach old records (all 772 role records are tag version 1).
6. Privacy (next): seat company + title + hire month can identify a person. Replace the dedupe key with an HMAC,
   coarsen hire date to the quarter, never display company or title, show a stratum only with 5+ holders from 3+
   employers.
7. Other sources (later): SEC 8-K item 5.02 and proxy bios (exact hire dates, C-suite), press moves (prior employer
   and tier; stored as hire events), users' own CV + LinkedIn with a separate consent (comparison group and outcomes;
   never in their own cohort; used from 5 contributed rows; at most 30% of a cohort).
8. LinkedIn terms: the User Agreement prohibits automated access to profiles; hiQ v. LinkedIn held such terms
   enforceable as contract. Owner decision whether collection through the owner's session continues.

## B. Job discovery
1. Per-user discovery (next): resolve each target company to its board (cached map -> probe board APIs with slug
   variants -> careers page links). Public JSON without a key: Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee
   (verified in documentation); Workable and Workday's cxs endpoint are unverified. Industries -> company lists shared
   across users. Title filter built from each user's target roles (today a fixed commercial filter; 10 boards seeded).
2. Balance: no company above 15% of a user's open postings; at most 3 per company in the top 20.
3. Dedupe by (company, title, location) with near-identical description.

## C. Job-based scoring
1. Requirement reading for any function (next): one read per posting (not three) returning core fields (level, years,
   scope, people management, education, location, authorization, domain) and open-vocabulary requirements, each with a
   verbatim quote, its section and required / preferred as the posting words it; mapped to ESCO and O*NET (free
   licences). Quote must be an exact substring. Cost about $0.001 per posting; fold the level assessment in.
2. Matching evidence to a requirement: same skill id; else local embedding similarity (>= 0.80 match, < 0.55 no
   match; thresholds are judgments to calibrate on 50 labeled postings); in between, an LLM that must return the
   posting quote and the CV line. Cached.
3. Fit formula: R = (sum m_req + 2 mu_req) / (N_req + 2), P likewise for preferred; fit = 100 (0.75 R + 0.25 P);
   mu = your own average match in that role family, so a short list does not score high. Shown as "meets 5 of 6
   required; 3.5 of 7 preferred" with the quote for each gap. A required core item at zero is a flag. Under half read:
   "partly read", no number. Caution from outside evidence: postings are a weak guide to what employers enforce, so the
   required / preferred split is shown first and weighted only after outcomes confirm it.
4. Feedback: record saved / dismissed / applied / interview / offer now; Bayesian bonus per company, role and level;
   logistic ranking only from 100 outcomes.
5. Per posting peer statement: "position X among N holders of this role at this level band (provisional under 20)";
   no per-posting edge is claimed (validation AUC 0.37-0.50).
