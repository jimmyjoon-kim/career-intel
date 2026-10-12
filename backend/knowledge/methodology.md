# How Career Intel scores competitiveness

## Taxonomy
Every job description, hire profile and CV is normalised into one taxonomy: sector, role cluster, level band and requirement tags. Requirement tags describe what a candidate must have: domain, function, management scale, education and skills. Scope, market, sponsorship, work-authorisation text and tenure are attributes of a posting, not requirements. Tenure is held as one ordinal field (years required).

## Gate
Before any scoring, each posting passes or fails a gate. The gate is pass/fail and never a number. A posting fails when:
- its level is below the candidate's minimum level (Head of is treated as Director-equivalent);
- its title contains a term the candidate has excluded;
- it is outside the candidate's locations and is not remote-eligible;
- it states no visa sponsorship and the candidate needs sponsorship;
- it is not confirmed open on the company's live job board (closed, stale or unverified).

## Discrimination weights
Within each role cluster, each requirement tag is classified by how often it appears in open postings:
- Common minimum: in 70% or more of postings. Weight 0, because nearly everyone hired has it, but it acts as a threshold.
- Mid: in 30% to 70% of postings. Weight 1.
- Discriminator: in fewer than 30% of postings. Weight 3, because it separates candidates.
Clusters with fewer than 8 open postings are merged into the nearest larger cluster by tag overlap, so that percentages rest on a usable sample.

## Match and rank
The candidate scores each tag 1 (clearly evidenced), 0.5 (partial) or 0 (absent), with evidence from the CV; the candidate can correct any score. Weighted score is the sum of weight times match divided by the sum of weights, over the posting's mid and discriminator tags. Hard gaps are common-minimum tags scored below 1. Postings with any hard gap scored 0 rank below all others; each hard gap scored 0.5 subtracts 0.10 from the rank score.

## Gap closing
Gaps are aggregated across gate-passing postings. Impact is frequency times weight times shortfall (hard gaps count 5). Each gap shows whether it is typically closable within about twelve months and how.

## Learning from outcomes
Weights are validated against the profiles of people actually hired, not job-description text alone. While the number of observed hires is small, weights are updated in a Bayesian way; once there are at least 100 hires, a logistic ranking model can be fitted.

## Rules
- Facts only. Verified and unverified information are kept separate.
- No probabilities or likelihoods of being hired are produced.
- Gaps are shown with their evidence and whether they can be closed; negatives are not over-weighted.
