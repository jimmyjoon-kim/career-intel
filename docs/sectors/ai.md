# Sector brief: AI (emphasis on agentic AI)

As of 2026-11-02. Labels: **[V]** = verified against a fetched source (secondary press unless noted as primary). **[U]** = unverified (reported by one secondary source, conflicting, or not confirmed). Run-rate figures are company-reported annualized numbers, not audited revenue.

## 1. Value chain and business models

| Layer | Examples | How it makes money |
|---|---|---|
| Compute / semiconductors | NVIDIA, AMD, Broadcom, TSMC, SK hynix | Chip and system sales to hyperscalers, neoclouds, and labs |
| Cloud / hyperscalers | AWS, Azure, Google Cloud, Oracle; neoclouds (CoreWeave, Nebius) | Compute rental; model access through managed platforms (Bedrock, Vertex AI, Foundry); marketplace resale |
| Frontier labs | OpenAI, Anthropic, Google DeepMind, Meta, SpaceXAI (formerly xAI), Mistral | API usage (per token), consumer subscriptions, enterprise seats/contracts, ads (OpenAI only so far) |
| Model platforms / inference | Hugging Face, Together AI, Fireworks AI, Baseten | Usage-based inference, hosting, enterprise plans |
| Data and tooling | Scale AI, Databricks, Snowflake, LangChain | Data labeling services, consumption-priced data platforms |
| Agentic platforms / apps | Sierra, Decagon, Cursor, Cognition, Salesforce Agentforce, Glean | Seats, usage credits, per-conversation, or per-outcome pricing |
| AI search / assistants | ChatGPT, Gemini, Perplexity, Meta AI | Subscriptions, usage credits, ads |

Key data points:
- NVIDIA Q2 FY2027 (quarter ended 2026-07-26): revenue $96.2B (+106% YoY); data center $89.0B (+117%); Q3 guide $108.0B ±2%. [V, primary] ([NVIDIA](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Second-Quarter-Fiscal-2027/))
- Cloud, Sept 2026 quarter: Azure $33.2B (+48% cc); Google Cloud $30.7B (+103%, includes Workspace), backlog $561B. AWS figure not confirmed by the same source. [U] ([Tech Insider](https://tech-insider.org/cloud-market-share-aws-azure-google-cloud-q3-2026-growth-gap-2026/))
- Databricks: >$7B run-rate, >80% YoY growth in Q2, $5B raise at $190B valuation (2026-08-13). [V] ([The Star/Reuters](https://www.thestar.com.my/tech/tech-news/2026/08/13/databricks-valued-at-190-billion-in-latest-funding-round))
- Meta invested $14.3B for 49% of Scale AI; CEO Alexandr Wang joined Meta (June 2025). [V] ([Maginative](https://www.maginative.com/meta-bets-14-3-billion-on-scale-ai-and-its-ceo-to-lead-new-superintelligence-lab/))

## 2. Agentic AI commercially (2025–2026)

**What is sold:** software "co-workers" that execute multi-step work (coding, customer service resolution, back-office tasks), deployed into enterprise systems, often with forward-deployed engineers.

**Main players and GTM:**
- **OpenAI Frontier** (launched Feb 2026): platform for building and orchestrating AI co-workers. "Frontier Alliances" with McKinsey, BCG (strategy/change) and Accenture, Capgemini (implementation), plus OpenAI forward-deployed engineers. [V] ([SiliconANGLE](https://siliconangle.com/2026/02/23/openai-allies-4-big-consulting-giants-agentic-enterprise-battle-heats/))
- **Anthropic:** Claude Partner Network (Mar 2026, $100M for 2026; anchors Accenture, Deloitte, Cognizant, Infosys); plans a fivefold increase in partner-facing headcount; Claude is available on Bedrock, Vertex AI, and Azure Foundry. Claude Code >$2.5B run-rate by Feb 2026. [V] ([TechTimes](https://www.techtimes.com/articles/317530/20260601/anthropic-enterprise-hiring-tops-research-ipo-filing-reveals-commercial-shift.htm))
- **Customer-service agents:** Sierra reports >$400M ARR (2026-10-30), added >$150M in Q3, valuation >$15B (May 2026 raise of $950M), serves "almost 50% of the Fortune 50" (self-reported). [V, self-reported] ([FourWeekMBA](https://fourweekmba.com/ai-sierra-hits-400m-arr-after-adding-150m-in-one-quarter/)). Decagon: $250M Series D at $4.5B (Jan 2026); $35M ARR as of Oct 2025. [U] ([AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/17/decagon-250m-series-d-4-5b-valuation-support-agent-vertical))
- **Coding agents:** Cursor (Anysphere) ~$3B ARR (May 2026); acquired by SpaceX in an all-stock deal implying $60B, closed 2026-08-14. [V] ([Wikipedia](https://en.wikipedia.org/wiki/Cursor_(company)))
- **Incumbent SaaS:** Salesforce Agentforce, ServiceNow, Workday, Microsoft. Their shares fell on concern that buyers will pick lab-native agents. [V] (SiliconANGLE, above)

**Pricing models observed:**
- Per seat / per user: Agentforce user license $5/user/month; flat-fee access $125/user/month. [V] ([LetsDataScience](https://letsdatascience.com/news/salesforce-expands-consumption-pricing-for-agentforce-5cc905f5))
- Per conversation / per resolution: Agentforce $2 per conversation; Decagon per-conversation by default with outcome layers. [V]/[U]
- Usage credits: Agentforce Flex Credits $500 per 100,000 credits; Perplexity moved to credits plus overage. [V]
- Per outcome: Sierra charges "for outcomes, not tokens" (e.g., claim paid, sale closed). [V, self-reported]
- Risk signal: Gartner (June 2025) predicted that more than 40% of agentic AI projects will be canceled by end of 2027. [V, multiple outlets] ([SD Times](https://sdtimes.com/agentic-ai/gartner-more-than-40-of-agentic-ai-projects-will-be-canceled-in-next-few-years/))

## 3. Commercial roles at AI companies

**Volume:** Sales is ~20% of Anthropic open roles; in late May 2026 Anthropic listed 72 open sales roles vs. 67 research/engineering. GTM is OpenAI's largest hiring category. [V] (TechTimes; [GTM Newsletter](https://thegtmnewsletter.substack.com/p/anthropic-and-openai-are-hiring-gtm))

**Role types:**
- *Enterprise AE / strategic sales:* multi-stakeholder, long cycles. Anthropic's most-hired role. Example: mid-market AE OTE $290K–$360K. [V]
- *Partnerships (GSI / SI / cloud):* joint business plans, co-sell, certification programs, multi-year commit deals.
- *Forward-deployed engineers / applied AI / "technical ambassadors":* technical deployment staff attached to sales. [V]
- *Ads sales (OpenAI):* agency and large-advertiser relationships, SMB via outsourcers (TP, Concentrix, Accenture). [V] ([Dealroom](https://dealroom.co/news/info-1aohyvh-openai-accelerates-ad-sprint-with-meta-hires-slashed-prices/))

**Feeder companies (sourced):**
- Anthropic GTM hires since start of 2026 (Crustdata): Salesforce 49, Google 31, Stripe 31, AWS 30, Databricks 26, Snowflake 18, Glean 11. The Information: >45 from Salesforce to Anthropic, ~40 to OpenAI. [V] ([Salesforce Ben](https://www.salesforceben.com/why-anthropic-is-raiding-salesforce-for-sales-talent/))
- Anthropic CCO Paul Smith (Aug 2025) came from ServiceNow. [V]
- OpenAI ads: Dave Dugan (ex-Meta VP global clients and agencies) joined as VP global ad solutions (Mar 2026). Meta is the largest source of ~70 ad-team hires July–Sept 2026; ad team ~140. Fidji Simo (ex-Meta/Instacart) is CEO of Applications. [V] ([Yahoo/Reuters](https://finance.yahoo.com/sectors/technology/articles/openai-hires-former-meta-executive-150400254.html); Dealroom)
- OpenAI Korea head Kim Kyoung-hoon is ex-Head of Google Korea (Sept 2025). Anthropic Korea Representative Director KiYoung Choi has "three decades" in Korean tech. [V] ([Korea Times](https://www.koreatimes.co.kr/amp/business/tech-science/20250929/openai-taps-ex-google-korea-chief-to-spearhead-seoul-office); [Anthropic](https://www.anthropic.com/news/seoul-office-partnerships-korean-ai-ecosystem))

**Typical posting requirements (Anthropic examples):**
- *Senior Partner Account Manager, GSI Alliances* (SF/NY, OTE $300K–$365K): 15+ yrs alliances/partner sales/consulting; 8+ yrs owning a top-tier GSI relationship at a hyperscaler or enterprise software/AI company; scaled a partner practice to $500M–$1B+; closed nine-figure multi-year agreements; GSI economics fluency; NA/EMEA/APAC experience including India delivery. Preferred: hands-on Claude/LLM architecture familiarity. [V] ([Accel job board](https://jobs.accel.com/companies/anthropic/jobs/66991898-senior-partner-account-manager-global-systems-integrator-alliances))
- *Head of Partner Sales, SIs* (OTE $355K–$425K): 10+ yrs partner/BD/enterprise sales; 5+ yrs managing partner teams; revenue through SIs; preferred AI/cloud ecosystem and consumption/API-model familiarity. [V] ([listing](https://my-sponsored-job.jobboardly.com/jobs/head-of-partner-sales-e62b6492))
- Common: office ≥25% of time; visa sponsorship "available but not guaranteed." [V]

## 4. Market structure 2024–2026

**Labs: revenue and funding**
- Anthropic run-rate: ~$7B (Oct 2025) → ~$9B (end 2025) → >$47B (May 2026) → >$65B (end July 2026). [V] ([Bloomberg Gov](https://news.bgov.com/legal-ops-and-tech/anthropic-revenue-run-rate-surpasses-65-billion-ahead-of-ipo)). ~80% enterprise; >1,000 customers >$1M/yr (Apr 2026, Sacra). $65B Series H at $965B post-money (2026-05-28); confidential IPO filing 2026-06-01. [V] (TechTimes)
- OpenAI: ARR >$20B in 2025 (CFO, Jan 2026) [V]; ~$2B monthly revenue and $13.1B booked 2025; $122B round at $852B post-money (2026-03-31, SoftBank co-lead). [V] ([HL](https://www.hl.co.uk/shares/stock-market-news/company--news/openai-clinches-$122bn-funding-round,-pushing-valuation-to-$852bn)). Reported talks at $1.4T valuation (Sept 2026). [U]
- Perplexity: >$450M ARR (Mar 2026), valuation near $20B. [U] ([LetsDataScience](https://letsdatascience.com/news/perplexity-shifts-to-ai-agents-boosts-revenue-a76bce31))
- SpaceX acquired xAI (2026-02-02); rebranded SpaceXAI (July 2026). [V] ([Wikipedia](https://en.wikipedia.org/wiki/SpaceXAI))

**Major partnerships**
- Microsoft–OpenAI (2025-10-28): Microsoft holds ~27% (~$135B); technology access through 2032. [V] ([Tom's Guide](https://www.tomsguide.com/ai/microsoft-and-openai-announce-new-deal-and-microsoft-gets-27-percent-what-it-means-for-you))
- Amazon–Anthropic: $8B invested; Project Rainier on Trainium 2; Amazon is primary training partner. Google–Anthropic: up to 1M TPUs, >1 GW by 2026 (2025-10-23); Google invested $3B. [V] ([SiliconANGLE](https://siliconangle.com/2025/10/23/anthropic-strikes-multibillion-dollar-deal-google-access-million-tpus/))
- Microsoft/NVIDIA–Anthropic (2025-11-18): $30B Azure compute commitment; NVIDIA up to $10B, Microsoft up to $5B investment. [V, primary] ([Anthropic](https://www.anthropic.com/news/microsoft-nvidia-anthropic-announce-strategic-partnerships))

**Ads in AI assistants**
- ChatGPT ads test announced 2026-01-16 for US Free and Go ($8/month) tiers; launched Feb. [V] ([SiliconANGLE](https://siliconangle.com/2026/01/16/openai-start-testing-chatgpt-ads-across-free-go-tiers/))
- Self-serve ads manager beta and CPC (April); $1B annualized ad run-rate (late Aug); 2026 target $2.5B; >$100B goal by 2030; 60+ countries; ~60,000 advertisers (early Oct). [V] ([eMarketer](https://www.emarketer.com/content/openai-1-billion-ad-run-rate-puts-its-2026-target-within-closer-reach); Dealroom)
- Anthropic pledged no ads in Claude (2026-02-04). [V] ([MacRumors](https://www.macrumors.com/2026/02/04/anthropic-clause-no-ads))
- Google told advertisers that Gemini ads are targeted for 2026 (Dec 2025); separate from AI Mode ads. Rollout status not confirmed. [U] ([Adweek](https://www.adweek.com/media/google-gemini-ads-2026/))

**APAC expansion**
- OpenAI: Tokyo (first Asia office, 2024); Singapore (announced Oct 2024, Southeast Asia base); Seoul (Korean entity, announced May 2025). [V] ([KrASIA](https://kr-asia.com/chatgpt-maker-openai-expands-into-singapore-targets-apac-growth); Korea Times)
- Anthropic: Tokyo and Bengaluru, then Seoul (announced 2025-10-23, opened June 2026). APAC run-rate grew >10x in the prior year (Oct 2025). Korean customers include NAVER, Samsung SDS, LG CNS, Nexon, Hanwha Solutions. [V, primary] ([Anthropic](https://anthropic.com/news/seoul-becomes-third-anthropic-office-in-asia-pacific))

## 5. Implications for assessing candidates from adjacent sectors

Sourced points only:
- **Transfers:** enterprise sales into cautious buyers (procurement, security review, multi-year deals) and existing CIO/CDO relationships. This is the stated reason Anthropic hires from Salesforce. [V] (Salesforce Ben)
- **Transfers:** quota ownership and pipeline discipline. [V] ([SaaStr](https://saastr.com/sales-in-the-age-of-ai-the-playbook-from-the-cros-of-databricks-windsurf-perplexity-and-owner/), self-reported)
- **Transfers (ads):** Meta/Google agency and large-advertiser relationships are the main source for OpenAI ads hiring. [V]
- **Transfers (partnerships):** GSI, hyperscaler, and consumption/API-model experience is listed as required or preferred. [V] (postings)
- **Gap signals:** AI fluency used as a hiring filter; technical depth (POCs, pilots); hands-on LLM familiarity preferred; relationship-led selling valued less than expertise. [V, SaaStr is a promotional source]
- **Gap signals:** senior partner postings require 8+ years owning a top-tier GSI relationship and nine-figure deal history, which candidates from mobile or ad tech typically will not have unless they held alliance roles. [V] (requirements); applicability per candidate is assessed separately.
- **Not found:** no sourced report specifically on mobile-ad-tech-to-AI transitions. [U]

Seed data: `backend/seed/sector_ai.json`.
