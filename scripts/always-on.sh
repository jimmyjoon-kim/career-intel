#!/bin/zsh
# Career Intel: run unattended on this Mac (24/7).
#   ./scripts/always-on.sh            install or refresh everything (safe to re-run)
#   ./scripts/always-on.sh --remove   remove the background agents (containers keep running)
# What it does (no sudo needed):
#   1. Adds any missing agent settings to .env (never changes existing values).
#   2. Sets Docker Desktop to start at login.
#   3. Builds and starts the app (db, api, web, worker).
#   4. Installs three login agents (launchd):
#        com.careerintel.keepalive  every 10 min: start Docker if needed, "docker compose up -d"
#        com.careerintel.update     daily 05:30: git pull (fast-forward only) and rebuild if code changed
#        com.careerintel.awake      keeps the Mac from sleeping while on power (caffeinate -s)
#   5. Adds the Claude app to login items (needed for the monthly hire-research task).
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LA="$HOME/Library/LaunchAgents"
LOG="$HOME/Library/Logs/career-intel"
UID_N=$(id -u)
mkdir -p "$LA" "$LOG"

if [[ "$1" == "--remove" ]]; then
  for n in keepalive update awake; do
    launchctl bootout "gui/$UID_N/com.careerintel.$n" 2>/dev/null || true
    rm -f "$LA/com.careerintel.$n.plist"
  done
  echo "Background agents removed. Containers are still running (docker compose down to stop them)."
  exit 0
fi

for d in /Applications/Docker.app/Contents/Resources/bin "$HOME/.docker/bin" /usr/local/bin /opt/homebrew/bin; do
  [[ -x "$d/docker" ]] && export PATH="$d:$PATH"
done
command -v docker >/dev/null || { echo "Docker Desktop is not installed: https://www.docker.com/products/docker-desktop/ (install, open once, re-run)"; exit 1; }
cd "$REPO"

# 1. .env: add agent settings that are missing
[[ -f .env ]] || cp .env.example .env
for kv in MODEL_BULK=claude-haiku-5-5 MODEL_CRITICAL=claude-fable-5-1 MODEL_CRITICAL_FALLBACK=claude-opus-5-5 \
          API_MONTHLY_ALLOWANCE_USD=20 BUDGET_SHARE=0.5 AGENTS_ENABLED=true; do
  grep -q "^${kv%%=*}=" .env || { echo "$kv" >> .env; echo "  .env: added $kv"; }
done
mkdir -p inbox
if ! grep -qE "^ANTHROPIC_API_KEY=.+" .env; then
  echo "  No Anthropic API key in .env: running ./setup.sh to enter keys and load data."
  ./setup.sh
fi

# 2. Docker Desktop starts at login (macOS may block scripts from editing Docker's settings; then set it by hand)
DOCKER_AUTOSTART=""
for f in "$HOME/Library/Group Containers/group.com.docker/settings-store.json" \
         "$HOME/Library/Group Containers/group.com.docker/settings.json"; do
  if [[ -f "$f" ]]; then
    if /usr/bin/python3 - "$f" <<'PY' 2>/dev/null
import json, sys
p = sys.argv[1]; d = json.load(open(p))
key = "AutoStart" if "settings-store" in p else "autoStart"
if d.get(key) is not True:
    d[key] = True; json.dump(d, open(p, "w"), indent=2)
PY
    then DOCKER_AUTOSTART="on"; else DOCKER_AUTOSTART="manual"; fi
    break
  fi
done
[[ "$DOCKER_AUTOSTART" == "manual" ]] && echo "  Docker Desktop: macOS blocked the settings change; turn on Settings > General > 'Start Docker Desktop when you sign in'."

# 3. Start Docker if needed, then the app
open -ga Docker || true
for i in {1..60}; do docker info >/dev/null 2>&1 && break; sleep 3; done
docker info >/dev/null 2>&1 || { echo "Docker did not start; open Docker Desktop and re-run."; exit 1; }
docker compose up -d --build
for i in {1..60}; do curl -fs localhost:8000/api/health >/dev/null 2>&1 && break; sleep 2; done
n=$(docker compose exec -T db psql -U career -d career_intel -tAc "select count(*) from reference_profiles" 2>/dev/null || echo 0)
if [[ "${n//[^0-9]/}" == "0" || -z "${n//[^0-9]/}" ]]; then
  echo "  Empty database: loading postings and role holders."
  docker compose exec -T api python -m app.seed
fi

# 4. Helper scripts and login agents
DOCKER_DIR="$(dirname "$(command -v docker)")"
cat > "$REPO/scripts/.keepalive.sh" <<SH
#!/bin/zsh
export PATH="$DOCKER_DIR:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
cd "$REPO"
docker info >/dev/null 2>&1 || { open -ga Docker; for i in {1..40}; do docker info >/dev/null 2>&1 && break; sleep 3; done; }
docker compose up -d >/dev/null 2>&1 && echo "\$(date '+%F %T') ok" || echo "\$(date '+%F %T') compose up failed"
SH
cat > "$REPO/scripts/.update.sh" <<SH
#!/bin/zsh
export PATH="$DOCKER_DIR:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
cd "$REPO"
before=\$(git rev-parse HEAD)
git pull --ff-only -q || { echo "\$(date '+%F %T') git pull failed (local changes?)"; exit 0; }
after=\$(git rev-parse HEAD)
if [[ "\$before" != "\$after" ]]; then
  docker compose up -d --build && echo "\$(date '+%F %T') updated to \$after" || echo "\$(date '+%F %T') rebuild failed; previous containers keep running"
else
  echo "\$(date '+%F %T') no change"
fi
SH
chmod +x "$REPO/scripts/.keepalive.sh" "$REPO/scripts/.update.sh"

plist() {  # name, program-args-xml, schedule-xml
  cat > "$LA/com.careerintel.$1.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.careerintel.$1</string>
  <key>ProgramArguments</key><array>$2</array>
  $3
  <key>StandardOutPath</key><string>$LOG/$1.log</string>
  <key>StandardErrorPath</key><string>$LOG/$1.log</string>
</dict></plist>
PL
  launchctl bootout "gui/$UID_N/com.careerintel.$1" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_N" "$LA/com.careerintel.$1.plist"
}
plist keepalive "<string>/bin/zsh</string><string>$REPO/scripts/.keepalive.sh</string>" \
  "<key>RunAtLoad</key><true/><key>StartInterval</key><integer>600</integer>"
plist update "<string>/bin/zsh</string><string>$REPO/scripts/.update.sh</string>" \
  "<key>StartCalendarInterval</key><dict><key>Hour</key><integer>5</integer><key>Minute</key><integer>30</integer></dict>"
plist awake "<string>/usr/bin/caffeinate</string><string>-s</string><string>-i</string>" \
  "<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>"

# 5. Claude app at login (the monthly hire-research task runs through it)
if [[ -d /Applications/Claude.app ]]; then
  osascript -e 'tell application "System Events" to if not (exists login item "Claude") then make login item at end with properties {path:"/Applications/Claude.app", hidden:true}' >/dev/null 2>&1 \
    && echo "  Claude app: opens at login" || echo "  Claude app: add it under System Settings > General > Login Items"
fi

echo
echo "Done. App: http://localhost:8080   Logs: $LOG"
echo "Sleep: the Mac now stays awake while on power with the lid open."
echo "Optional (asks for your password) so it also wakes for the network and survives a closed lid:"
echo "  sudo pmset -c sleep 0 disksleep 0 womp 1 && sudo pmset -a disablesleep 1"
