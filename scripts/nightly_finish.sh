#!/usr/bin/env bash
# Steps 2b + 3 + 4a: verify translations, build data files, generate the Vercel deploy payload.
set -euo pipefail
cd "$(dirname "$0")/.."
DATE="${1:-$(TZ=Asia/Tehran date +%F)}"
.venv/bin/python scripts/translate.py check "$DATE"
.venv/bin/python scripts/build.py "$DATE"
.venv/bin/python scripts/deploy_payload.py > /dev/null
echo "NEXT: deploy (see NIGHTLY.md step 4) using deploy/payload.json"
