#!/bin/sh
# Deploy on the Mac: pull, rebuild, then verify. Exits non-zero if the live app is not the pulled commit or a
# severity-1 health check fails, so a bad deploy is seen at once (run by the interactive session, checked by the steward).
set -e
cd "$(dirname "$0")/.."
git pull -q
export GIT_COMMIT="$(git rev-parse HEAD)"
docker compose up -d --build api worker web > backups/deploy.log 2>&1
sleep 6
LIVE="$(curl -s -m 10 localhost:8000/api/version | sed 's/.*"commit":"\([^"]*\)".*/\1/')"
echo "live commit: $LIVE (expected $(echo "$GIT_COMMIT" | cut -c1-12))"
[ "$LIVE" = "$(echo "$GIT_COMMIT" | cut -c1-12)" ] || { echo "DEPLOY CHECK FAILED: live commit differs"; exit 1; }
docker compose exec -T api python -c "
from app.db import SessionLocal
from app.agents import health
with SessionLocal() as db:
    r = health.run(db, None)
    print('health:', r['checks'], 'checks; failed:', r['failed'])
    raise SystemExit(1 if r['sev1_failed'] else 0)
" || { echo "DEPLOY CHECK FAILED: severity-1 health check"; exit 1; }
echo "deploy ok"
