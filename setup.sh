#!/usr/bin/env bash
# One-command setup: ./setup.sh
# Starts Docker if needed, asks for API keys once, builds, loads sample data, opens the app.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf "\n\033[1;36m▶ %s\033[0m\n" "$1"; }

# 1. Docker — find the CLI even when Docker Desktop has not added it to PATH
for d in /Applications/Docker.app/Contents/Resources/bin "$HOME/.docker/bin" /usr/local/bin /opt/homebrew/bin "$HOME/.orbstack/bin"; do
  [ -x "$d/docker" ] && case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
done
export PATH
command -v docker >/dev/null || { echo "Docker CLI not found. Install Docker Desktop from docker.com, open it once, then re-run ./setup.sh"; exit 1; }

if ! docker info >/dev/null 2>&1; then
  say "Waiting for the Docker engine (finish any Docker Desktop setup screens)…"
  open -a Docker 2>/dev/null || open -a OrbStack 2>/dev/null || true
  for _ in $(seq 1 150); do docker info >/dev/null 2>&1 && break; sleep 2; done
  if ! docker info >/dev/null 2>&1; then
    echo "Docker engine is not responding. Docker says:"
    docker info 2>&1 | tail -5
    exit 1
  fi
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "'docker compose' is missing. Update Docker Desktop, then re-run ./setup.sh"; exit 1
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
