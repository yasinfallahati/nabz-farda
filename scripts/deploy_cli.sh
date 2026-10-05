#!/usr/bin/env bash
# Primary deploy path: Vercel CLI with $VERCEL_TOKEN. public/ is linked to project nabz-farda (yasin-e51b).
set -euo pipefail
cd "$(dirname "$0")/../public"
: "${VERCEL_TOKEN:?VERCEL_TOKEN is not set}"
mkdir -p /home/box/.local/lib
npx --yes vercel@latest deploy --prod --yes --token "$VERCEL_TOKEN"
rm -f .env.local
