#!/usr/bin/env bash
# One-command setup: ./setup.sh
# Starts Docker if needed, asks for API keys once, builds, loads sample data, opens the app.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf "\n\033[1;36m▶ %s\033[0m\n" "$1"; }

# 1. Docker
if ! docker info >/dev/null 2>&1; then
  say "Starting Docker…"
  open -a Docker 2>/dev/null || open -a OrbStack 2>/dev/null || { echo "Docker is not installed."; exit 1; }
  for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || { echo "Docker did not start. Open Docker Desktop, then re-run ./setup.sh"; exit 1; }
fi

# 2. API keys (asked once; press Enter to skip and run in offline mode)
if [ ! -f .env ]; then
  cp .env.example .env
  say "API keys (input hidden; press Enter to skip)"
  read -rsp "Anthropic API key: " AK; echo
  read -rsp "Voyage API key:    " VK; echo
  SECRET=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40)
  sed -i.bak -e "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${AK}|" \
             -e "s|^VOYAGE_API_KEY=.*|VOYAGE_API_KEY=${VK}|" \
             -e "s|^JWT_SECRET=.*|JWT_SECRET=${SECRET}|" .env && rm -f .env.bak
fi

# 3. Build and start
say "Building and starting (first run takes a few minutes)…"
docker compose up --build -d

say "Waiting for the API…"
for _ in $(seq 1 90); do curl -fs localhost:8000/api/health >/dev/null 2>&1 && break; sleep 2; done
curl -fs localhost:8000/api/health >/dev/null || { echo "API did not start. Logs:"; docker compose logs --tail=40 api; exit 1; }

# 4. Load sample postings and build the search index
say "Loading postings and building the index…"
docker compose exec -T api python -m app.seed

say "Ready → http://localhost:8080  (the first account you create is the admin)"
open http://localhost:8080
