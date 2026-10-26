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

# 2. API keys — asked whenever they are blank in .env (press Enter to skip = offline mode)
[ -f .env ] || cp .env.example .env
getv() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }
setv() {
  if grep -qE "^$1=" .env; then
    awk -v k="$1" -v v="$2" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' .env > .env.tmp && mv .env.tmp .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}
if [ -z "$(getv ANTHROPIC_API_KEY)" ] || [ -z "$(getv VOYAGE_API_KEY)" ]; then
  say "API keys — paste each one and press Enter (nothing shows while you paste; Enter alone skips)"
  if [ -z "$(getv ANTHROPIC_API_KEY)" ]; then read -rsp "Anthropic API key: " AK; echo; [ -n "$AK" ] && setv ANTHROPIC_API_KEY "$AK"; fi
  if [ -z "$(getv VOYAGE_API_KEY)" ]; then read -rsp "Voyage API key:    " VK; echo; [ -n "$VK" ] && setv VOYAGE_API_KEY "$VK"; fi
fi
case "$(getv JWT_SECRET)" in ""|change-me) setv JWT_SECRET "$(openssl rand -hex 20)" ;; esac
echo "Claude: $([ -n "$(getv ANTHROPIC_API_KEY)" ] && echo on || echo 'off (offline mode)') · Voyage: $([ -n "$(getv VOYAGE_API_KEY)" ] && echo on || echo 'off (local embeddings)')"

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
