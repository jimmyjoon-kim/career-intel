# Career Intel

Measures a candidate's competitiveness for senior commercial roles against live job postings, and answers
questions about it from cited sources.

- **Multi-user.** Each user has a private CV, evidence and gate preferences. Postings are a shared dataset that admins maintain.
- **Gate, then score.** Postings first pass or fail on level, excluded title terms, location/remote, sponsorship need and live status. Only passing postings are ranked.
- **Market-derived weights.** In each role cluster, requirements in ≥70% of postings are *common minimums* (weight 0, but a threshold), 30–70% are *mid* (weight 1), and <30% are *discriminators* (weight 3). Clusters with fewer than 8 postings merge into the nearest cluster by tag overlap.
- **RAG.** Postings, per-cluster market summaries, the method document, the user's CV and a generated scorecard are embedded with Voyage and stored in pgvector. Claude answers only from the retrieved sources, with inline citations. It never states hiring probabilities.
- **Offline mode.** Without API keys the app still runs. Tags come from keyword matching, embeddings from a local hashing model, and answers show sources only.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18, TypeScript, Vite, served by nginx |
| Backend | FastAPI, SQLAlchemy 2, JWT auth (bcrypt) |
| Data | Postgres 16 + pgvector |
| AI | Anthropic Claude (CV/JD tagging, answers); Voyage `voyage-3.5` embeddings (1024-d) |

## Run with Docker

One command (macOS): `./setup.sh` — starts Docker, asks for the API keys once, builds, loads the sample data and opens the app.

Manual steps:

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY and VOYAGE_API_KEY
docker compose up --build -d
docker compose exec api python -m app.seed   # load the sample postings and build the index
```

Open http://localhost:8080. The first account created is the admin. Upload a CV on **Profile** and set your gate preferences.

If you add or change API keys later, restart the API (`docker compose up -d api`) and press **Data → Rebuild** so the corpus is re-embedded with the new model.

## Run without Docker (development)

```bash
# Postgres 16 with the pgvector extension must be running and reachable at DATABASE_URL
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://career:career@localhost:5432/career_intel
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --reload

cd ../frontend && npm install && npm run dev     # http://localhost:5173, proxies /api to :8000
```

## Tests

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://career:career@localhost:5432/career_test .venv/bin/pytest -q
```

The scoring tests are pure Python. The API test runs the full flow against Postgres in offline mode: sign-up, admin import, CV upload, overrides, ranking, RAG privacy and closing a posting.

## Updating the market data

- **Data → Import weekly CSV** accepts the `postings_<date>.csv` format that the weekly scoreboard task writes. Rows are matched by URL. A row counts as `open` only when its `listed` column says `LISTED`; unverifiable rows are kept but fail the gate.
- **Data → Add a posting** tags a pasted job description automatically.
- `PATCH /api/admin/postings/{id}?status=closed` marks a posting closed.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/signup`, `/api/auth/login` | Returns a JWT |
| GET/PUT | `/api/profile` | Profile and gate preferences (PUT with `cv_text` re-extracts) |
| POST | `/api/profile/cv` | Upload a PDF/DOCX/TXT CV |
| PUT | `/api/profile/tags/{tag}` | Override a requirement match (0, 0.5, 1) with evidence |
| GET | `/api/dashboard` | KPIs, top matches, aggregated gaps, gate-failure reasons |
| GET | `/api/postings`, `/api/postings/{id}` | Gated and scored postings |
| GET | `/api/market` | Requirement statistics per cluster |
| POST | `/api/ask` | Grounded question answering with sources |
| POST | `/api/admin/import`, `/api/admin/postings`, `/api/admin/reindex` | Admin data management |

Interactive docs are served at `http://localhost:8000/docs`.

## Not yet built

- Hire-profile ingestion and Bayesian re-weighting from outcomes. The method is described in `backend/knowledge/methodology.md`; the data model has room for it.
- Database migrations. Tables are created on start-up; add Alembic before the schema changes in production.
- Email verification, password reset and rate limiting, which are needed before public launch.
