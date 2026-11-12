# Backlog (rank = impact x confidence / effort; the steward re-ranks weekly)
| id | source | finding | impact | conf | effort | rank | owner? | done when | status |
|---|---|---|---|---|---|---|---|---|---|
| B01 | plan C1 | Requirement reading is commercial-only, reads each posting 3x, no quotes, no required / preferred | 5 | 0.9 | 3 | 1.5 | N | one read per posting with exact quotes; precision / recall on 50 labeled postings recorded | next |
| B02 | plan C3 | Fit formula rewards short requirement lists; weights from posting frequency | 4 | 0.8 | 2 | 1.6 | Y (moves fit) | new formula with before / after on all postings | after B01 |
| B03 | plan B1 | Job discovery: 10 seeded boards, fixed commercial title filter, one company = 18% of postings | 5 | 0.8 | 3 | 1.3 | N | largest company <= 15%; companies per user reported | next |
| B04 | plan A1 | Peer group mixes hire years 2003-2026, regions and levels | 4 | 0.7 | 3 | 0.9 | Y (moves scores) | cohort line shown; effective n reported | later |
| B05 | council 1 | Golden profiles + monotonicity probes in CI; before / after script | 4 | 0.9 | 2 | 1.8 | N | CI fails on a > 3 point move without a changelog row | next |
| B06 | council 3 | Hourly collector starts a top-priced session ~20x a day, mostly for nothing | 3 | 0.9 | 1 | 2.7 | Y (schedule) | gated first step; 3 windows a day; standard model | proposed |
| B07 | plan A6 | Seat company + title + hire month can identify a person | 4 | 0.8 | 2 | 1.6 | N | hashed dedupe key; hire date by quarter; strata >= 5 holders / 3 employers | next |
| B08 | plan A4 | No comparison group: validation compares winners with winners | 5 | 0.6 | 3 | 1.0 | Y (LinkedIn volume) | earlier-hire events derived; 10 one-level-below per role | later |
| B09 | council 3 | No backups check; Postgres on one Mac | 4 | 0.9 | 1 | 3.6 | N | nightly pg_dump; health check on its age | next |
| B10 | council 2 | Text-read factors grow with text length; user read from CV + LinkedIn, holders from LinkedIn only | 3 | 0.7 | 3 | 0.7 | Y | evidence weighted by role months | later |
