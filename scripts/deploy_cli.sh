#!/usr/bin/env bash
# Primary deploy path: Vercel CLI with $VERCEL_TOKEN → project nabz-farda (yasin-e51b).
set -euo pipefail
cd "$(dirname "$0")/../public"
: "${VERCEL_TOKEN:?VERCEL_TOKEN is not set}"
# Keep link pinned so a missing .vercel/ never creates a stray project named "public".
mkdir -p .vercel
cat > .vercel/project.json <<'JSON'
{"projectId":"prj_FI7HMxELR3xUgZjqkCBFfgqapK8c","orgId":"team_k34pVoV91wnUatXZsYOOdTVd","projectName":"nabz-farda"}
JSON
mkdir -p /home/box/.local/lib
npx --yes vercel@latest deploy --prod --yes --token "$VERCEL_TOKEN"
rm -f .env.local
