#!/bin/zsh
# Run on the NEW Mac: ./scripts/db-import.sh backups/career_intel_<date>.sql.gz
# Replaces this Mac's app database with the backup, then starts the app.
set -e
cd "$(dirname "$0")/.."; source scripts/_docker_path.sh
[[ -f "$1" ]] || { echo "Usage: ./scripts/db-import.sh backups/<file>.sql.gz"; exit 1; }
open -ga Docker 2>/dev/null || true
for i in {1..60}; do docker info >/dev/null 2>&1 && break; sleep 3; done
docker compose up -d db
for i in {1..40}; do docker compose exec -T db pg_isready -U career -d career_intel >/dev/null 2>&1 && break; sleep 2; done
docker compose stop api worker >/dev/null 2>&1 || true
# Start from an empty schema so newer tables on this Mac cannot block the restore.
docker compose exec -T db psql -U career -d career_intel -q -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1
gunzip -c "$1" | docker compose exec -T db psql -U career -d career_intel -q 2>&1 | grep ERROR | grep -v "does not exist" | head -5 || true
# restart the app so it adds any columns/tables the backup's older version lacked
docker compose up -d >/dev/null 2>&1 && docker compose restart api worker >/dev/null 2>&1 || true
n=$(docker compose exec -T db psql -U career -d career_intel -tAc "select count(*) from users" 2>/dev/null)
echo "Restored $1 (${n//[^0-9]/} accounts). Next, if not done yet: ./scripts/always-on.sh"
