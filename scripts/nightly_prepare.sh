#!/usr/bin/env bash
# Steps 1 + 2a of the nightly run: fetch feeds and create the translation file for the AI agent to fill.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q feedparser requests beautifulsoup4; }
DATE="${1:-$(TZ=Asia/Tehran date +%F)}"
.venv/bin/python scripts/fetch_news.py --date "$DATE"
.venv/bin/python scripts/translate.py export "$DATE"
echo "NEXT: fill data/translations/$DATE.json (title_fa + summary_fa for every item), then run scripts/nightly_finish.sh $DATE"
