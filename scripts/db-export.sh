#!/bin/zsh
# Run on the OLD Mac: saves the whole app database (accounts, profile, role reviews, photo, runs) to backups/.
set -e
cd "$(dirname "$0")/.."; source scripts/_docker_path.sh
mkdir -p backups
f="backups/career_intel_$(date +%Y-%m-%d_%H%M).sql.gz"
docker compose exec -T db pg_dump -U career -d career_intel --clean --if-exists | gzip > "$f"
echo "Saved $f ($(du -h "$f" | cut -f1)). Copy it to the other Mac (AirDrop) into ~/career-intel/backups/."
