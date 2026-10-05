# نبض فردا (Nabz-e Farda) — Nightly refresh runbook

Runs every night at **00:00 Asia/Tehran**. Project root: `/workspace/news-site` (persistent box).
Production project on Vercel: **`nabz-farda`** → production URL **https://nabz-farda.vercel.app**
(always deploy with `target: "production"` to the same project so that URL is updated).

```
scripts/feeds.json        feed list (name, url, default category, optional max / require_keywords)
scripts/fetch_news.py     STEP 1  fetch + dedupe + categorize + select  -> data/raw/DATE.json
scripts/translate.py      STEP 2  export / check translation file       -> data/translations/DATE.json
scripts/build.py          STEP 3  merge -> public/data/days/DATE.json + public/data/archive.json, then calls
scripts/sitegen.py                static SEO layer for ALL days: public/news/DATE/ID.html (+ day pages, /news/ archive),
                                  public/og/DATE/ID.png (1200x630), sitemap.xml, sitemap-news.xml, robots.txt, feed.xml,
                                  plus competition artifacts: data/ops.json, data/search-index.json, api/v1/{latest,archive,ops,openapi}.json
scripts/telegram_post.py  STEP 6  post the night's best ~8 stories to the Telegram channel (state: data/telegram/posted.json)
scripts/deploy_payload.py STEP 4  requestBody for Vercel create_deployment -> deploy/payload.json
public/                   the static site (index.html, assets/, data/) — this folder is what gets deployed
```
DATE = Tehran calendar date of the run, `YYYY-MM-DD` (`TZ=Asia/Tehran date +%F`). Every day keeps its own
`public/data/days/DATE.json`, so the archive grows automatically; never delete old day files.

## Step 1 — Fetch
```bash
cd /workspace/news-site
DATE=$(TZ=Asia/Tehran date +%F)
scripts/nightly_prepare.sh "$DATE"      # = fetch_news.py --date $DATE  +  translate.py export $DATE
```
Expect: `items=36 counts={'ai': 12, 'game': 12, 'tech': 12}`. `WARN feed failed` lines are OK if only a
few feeds fail (they are retried 3x). If a category has <6 items, re-run with `--hours 48`:
`.venv/bin/python scripts/fetch_news.py --date $DATE --hours 48 && .venv/bin/python scripts/translate.py export $DATE`.

## Step 2 — Translate (done by the AI agent itself)
Open `data/translations/$DATE.json`. For **every** id, fill:
* `title_fa` — natural, journalistic Persian headline (keep product/company names in Latin where usual,
  e.g. OpenAI, PS5; use Persian punctuation « » ، ؛ and Persian digits ۰-۹ for numbers).
* `summary_fa` — 1–2 Persian sentences explaining the story, based on `_title` / `_summary`
  (fetch the article if `_summary` is empty). No invented facts. Used on home/list cards and the «خلاصه» block on the article page.
* `body_fa` — longer original Persian write-up for the article page «خبر کامل» section: roughly 3–6 short
  paragraphs (~150–400 Persian words), paragraphs separated by a blank line. Paraphrase from `_title` /
  `_summary` (and the linked article if needed); do not dump copyrighted English source text. Expand the
  summary without inventing wild facts.
* Optional: `"featured": true` on ONE strong story with an image (hero). Otherwise the newest item with an image is used.
* Optional: `"drop": true` for duplicates of the same story from two sources (keep the better one),
  deal/coupon posts, or off-topic items.
Only edit those fields; leave `_`-prefixed fields alone. Easiest: write a small Python dict
`{id: [title_fa, summary_fa, body_fa]}` and merge it into the file with a few lines of Python.

Then verify:
```bash
.venv/bin/python scripts/translate.py check "$DATE"     # must print N/N translated, exit 0
```

## Step 3 — Build
```bash
scripts/nightly_finish.sh "$DATE"   # = translate.py check + build.py DATE + deploy_payload.py
```
Expect: `built DATE: ~33 items (0 untranslated); archive has K day(s)`, then
`pages: N articles + K day pages; og images redrawn ~33; sitemap U urls; feed 60 items`, and
`# M files, X inlined, Y by sha -> deploy/payload.json`.

Also expect search-index / ops / api/v1 files under `public/` (written by sitegen every rebuild).
Static showcase pages (`automation/`, `about/`, `api/`, `search/`) and PWA files (`manifest.webmanifest`, `sw.js`) live in `public/` and deploy with the site.
Optional local check: `.venv/bin/python scripts/preview_server.py 8765` (mimics Vercel cleanUrls) then open
http://localhost:8765/ and an article, e.g. http://localhost:8765/news/$DATE/<id>.

## Step 4 — Deploy (Vercel connector, server `user-Vercel`)
1. Read `deploy/payload.json` — it is exactly the `requestBody` object.
2. Call MCP tool `user-Vercel` → `create_deployment` with arguments
   `{"skipAutoDetectionConfirmation": "1", "requestBody": <contents of deploy/payload.json>}`.
   * Files already on Vercel are referenced as `{file, sha, size}`; only new/changed files (normally
     `data/archive.json` + today's `data/days/DATE.json`) are inlined, which keeps the call small.
   * If Vercel answers `missing_files`, regenerate with `.venv/bin/python scripts/deploy_payload.py --all > /dev/null`
     (inlines everything) and call again.
3. Poll `get_deployment` (`idOrUrl` = returned id) until `readyState` is `READY` (≈10–30 s; static, no build step).
   If `ERROR`, read `list_deployment_events` for the reason.
4. Record what is now live (lets tomorrow's payload reference unchanged files by SHA):
   ```bash
   .venv/bin/python scripts/deploy_payload.py --mark-deployed https://nabz-farda.vercel.app
   ```
**Alternative (no MCP):** if a Vercel token is provided as `$VERCEL_TOKEN`, run `scripts/deploy_cli.sh`
(`npx vercel deploy public --prod --name nabz-farda`).

## Step 5 — Verify
```bash
curl -s https://nabz-farda.vercel.app/data/archive.json | head -c 300; echo   # "latest" must equal $DATE
curl -s -o /dev/null -w '%{http_code}\n' https://nabz-farda.vercel.app/      # 200
google-chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars --window-size=1440,2200 \
  --virtual-time-budget=15000 --screenshot=/workspace/news-site/screenshot.png https://nabz-farda.vercel.app/
```
Look at `screenshot.png`: Persian hero story + sections, "آخرین به‌روزرسانی" shows tonight's time.
If the root URL returns 401, Vercel Deployment Protection is on for production — disable it in
project settings (or via `update_project` with `ssoProtection: null`).

## Step 6 — Post to Telegram (after deploy + verify succeeded)
Channel: private «Nabz farda» (chat_id in `config/telegram.json`), bot @Nabz_farda_bot, token in env `TELEGRAM_BOT_TOKEN`
(never print it). Only run this once Step 5 shows tonight's DATE live; the script also checks that each article page and
its OG image return 200 before sending.
```bash
.venv/bin/python scripts/telegram_post.py nightly "$DATE" --dry-run     # review the 8 picks + captions
.venv/bin/python scripts/telegram_post.py nightly "$DATE"               # send them (~1.6 s apart)
```
* Picks ~8 stories (`--max N` to change): the featured story first, then a rotation over ai / tech / game ranked by the
  same notability score as the stories bar. If a pick is weak (recap, minor update), re-run the dry run with
  `--exclude ID [ID …]`; to post specific ones use `--id ID [ID …]`.
* Each one is a photo post using the OG image (`/og/DATE/ID.png`; falls back to uploading the local PNG, then the story
  image, then text). Caption (HTML): bold title, summary, category hashtag + #نبض_فردا, link to `/news/DATE/ID`,
  source name; buttons «📖 مطالعه در نبض فردا» and «منبع اصلی».
* State: `data/telegram/posted.json`. Ids already there are never posted again, so a re-run after a partial failure
  only sends what's missing. Expect `POSTED=8 FAILED=0`; exit 1 means some sends failed (the reasons are printed;
  just re-run). `telegram_post.py status` lists everything posted so far.
* Never run it for old dates to "catch up" unless the user asks: it would flood the channel.

## Troubleshooting
* Feed broken permanently → edit/remove it in `scripts/feeds.json` (test: `.venv/bin/python scripts/fetch_news.py --date test`, then delete `data/raw/test.json`).
* Wrong category → add keywords to `AI_KW` / `GAME_KW` in `fetch_news.py`, or `drop` it.
* Missed night → run the steps with that night's DATE; the archive sorts by date automatically.
* `.venv` missing → `python3 -m venv .venv && .venv/bin/pip install feedparser requests beautifulsoup4`.

## Deploy (preferred)
Run `bash scripts/deploy_cli.sh` (uses $VERCEL_TOKEN; project nabz-farda already linked). Live URL: https://nabz-farda.vercel.app — verify it returns 200 and shows today's date.

## Stories update (every 3 hours)
Instagram-style «استوری» bar under the header (above the hero). Data: `public/data/stories.json` (a JSON list of
`{id, title_fa, summary_fa, category, source, url, image, published, added_at, title}`); stories live **24h after
`added_at`**, max **15**. UI code: `public/assets/stories.js` + `stories.css` (the bar hides itself when no live story;
expired ones are also hidden client-side, so a deploy is never needed just to expire stories).
Script: `scripts/update_stories.py` (reuses `fetch_news.py`'s feed list + fetch code). Pending file: `data/stories/pending.json`
(applied ones are archived in `data/stories/applied/`). Suggested schedule: 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00
Tehran — skip 00:00 (the nightly run owns that slot; never run both at once, both deploy `public/`).

1. **Fetch candidates**
   ```bash
   cd /workspace/news-site
   .venv/bin/python scripts/update_stories.py fetch          # last 3h, max 8 candidates, min score 3
   ```
   * Prints `CANDIDATES=0` → **stop here. Do not apply, do not deploy.** The run is done.
   * Otherwise it lists `[score] id category source English-title` and writes `data/stories/pending.json`.
     Candidates already exclude anything in `stories.json` or today's day file (same id/URL or same story by title).
2. **Decide + translate (the AI agent).** Open `data/stories/pending.json`. For each candidate read `_title`, `_summary`,
   `_why` (why it scored: multi-outlet coverage, launch/breach/lawsuit keywords, official lab post, HN front page…).
   Keep only **genuinely notable / breaking** items — big launches, major company news, security incidents, lawsuits,
   big game reveals, records. Drop how-tos, reviews, opinion, deals, minor updates, near-duplicates: set `"drop": true`.
   It is fine (and normal) to keep 0–3 per run. For each kept item fill:
   * `title_fa` — short punchy Persian headline (≤ ~70 chars; Latin for product names; Persian digits ۰-۹; « » ،).
   * `summary_fa` — 1–2 Persian sentences, facts only (fetch the article URL if `_summary` is empty/thin).
   * optional: change `category` (`ai` | `tech` | `game`) if the feed's guess is wrong.
   * order: the first kept candidate in the file appears first in the bar.
   Edit only `title_fa`, `summary_fa`, `drop`, `category` (easiest: a small Python dict `{id: (title_fa, summary_fa)}` merged in).
   If you keep nothing, still run step 3 (it archives the pending file and exits without deploying).
3. **Apply + deploy (+ Telegram for breaking items)**
   ```bash
   .venv/bin/python scripts/update_stories.py apply --deploy --telegram
   ```
   `--telegram`: after `LIVE OK`, runs `telegram_post.py stories`, which sends a brief text post («🔴 فوری | title», summary,
   hashtag, source link) for each newly kept story flagged **breaking**. Flagging: set `"breaking": true` (or `false`)
   on a candidate in `pending.json` yourself; if you leave it out, it is automatic when `_score >= 6` and the title has a
   breaking keyword (launch / breach / lawsuit / …). Max 3 per run, only stories added in the last 6h, never twice
   (shared state `data/telegram/posted.json`). A Telegram failure prints `telegram: WARN` but never undoes the deploy.
   Preview: `.venv/bin/python scripts/telegram_post.py stories --dry-run`.
   Merges kept candidates (`added_at` = now), prunes stories older than 24h, keeps the newest 15, then checks the site
   (runs `build.py` for the latest day in a scratch copy, validates JSON / assets / JS syntax). Expect
   `site check OK`, `ADDED=N`.
   * `ADDED=0` → prints `nothing new -> no deploy` and exits 0. Done.
   * `ADDED>0` → runs `bash scripts/deploy_cli.sh` (Vercel CLI, `$VERCEL_TOKEN`, `public/` already linked to `nabz-farda`)
     and then polls the live `https://nabz-farda.vercel.app/data/stories.json` until it contains the new ids →
     `LIVE OK: ...`. If `$VERCEL_TOKEN` is missing, deploy via the MCP path of Step 4 instead
     (`.venv/bin/python scripts/deploy_payload.py > /dev/null`, then `create_deployment`, then `--mark-deployed`).
   * `site check FAILED` → fix the reported problem (never deploy a broken site); `stories.json` can be restored from
     the previous deploy with `curl -s https://nabz-farda.vercel.app/data/stories.json > public/data/stories.json`.
4. **Verify (optional, quick)** `.venv/bin/python scripts/update_stories.py status` (ages of live stories); open
   https://nabz-farda.vercel.app/ — the circles row shows the new stories with a gradient ring; `/#s=<id>` deep-links one.

Notes: first seed run used `fetch --hours 24 --include-today --max 12` (also allows items from today's day file) —
use that only if the bar is empty and nothing new qualifies. Tuning: `--hours`, `--max`, `--min-score`; keyword lists
`BREAKING` / `SOFT` / `BIG` in `update_stories.py`. The nightly pipeline is unaffected (it deploys `public/` including
`stories.json`, so current stories stay live across the nightly deploy).

## Article pages, SEO, OG images, analytics (added 2026-10-04)
* **Per-story pages** `/news/DATE/ID` (file `public/news/DATE/ID.html`; `public/vercel.json` has `cleanUrls: true`, so
  `.html` URLs 308-redirect to the clean URL). Each has Persian title/summary, English original title, source link,
  Tehran date, category, 4 related stories, share links, back link, canonical, OG/Twitter meta, JSON-LD `NewsArticle` +
  `BreadcrumbList`. Day pages `/news/DATE/`, archive `/news/`. Homepage/ticker/hero cards link to these pages
  (`app.js` uses the item's `page` field that build.py now writes, falling back to `/news/<day>/<id>`).
* **OG images** `public/og/DATE/ID.png` + `public/og/default.png` (PIL + raqm, Vazirmatn from `/workspace/insta/assets/fonts/`;
  override with `NF_FONTS`). Needs Pillow in .venv (`.venv/bin/pip install pillow`). Cached via `data/og-manifest.json`:
  only new/changed stories are redrawn. To force a full redraw after a design change, bump `OG_VERSION` in `sitegen.py`.
  Logos: `assets/logo-512.png`, `assets/apple-touch-icon.png`.
* **SEO files** `sitemap.xml` (home, archive, day pages, all articles), `sitemap-news.xml` (Google News, last 48h),
  `robots.txt`, `feed.xml` (RSS 2.0, newest 60, with OG image enclosure, usable for Telegram bots / Google News).
* Regenerate only the static layer (no raw file needed, e.g. after editing a translation or a template):
  `.venv/bin/python scripts/build.py --pages-only`. A story set to `"drop": true` after build gets its page/OG removed.
* **Web Analytics** (free, Hobby): enabled on project `nabz-farda` (2026-10-04, via `POST /web/insights/toggle`).
  Snippet `/_vercel/insights/script.js` is in index.html and every generated page. Dashboard: Vercel → nabz-farda → Analytics.
* `update_stories.py apply` site check now also verifies article pages/OG/sitemap/feed exist (it runs build.py in a
  scratch copy, copying `data/og-manifest.json` so nothing is redrawn). Stories still link to the source article.
* `deploy_payload.py` (MCP path) now sends PNGs as base64 and skips `.vercel/`; `--mark-deployed` only re-checks new SHAs.
* Extra verify: `curl -sI https://nabz-farda.vercel.app/news/$DATE/<id>` → 200; `/sitemap.xml`, `/feed.xml`, `/og/$DATE/<id>.png` → 200.

## Design (calm redesign, live since 2026-10-04)
`public/` + `scripts/sitegen.py` ARE the design source; routines just rebuild them, so nothing reverts the design.
Single accent `--acc` #ff5a4e on a neutral dark background (#0b0c0f) in `public/assets/style.css`. That file is shared by the
home page and the generated pages; page-only rules are in `article.css`. Homepage layout: header tabs (همه / هوش مصنوعی /
تکنولوژی / گیم, deep-linkable as `/?c=ai`), the stories bar, one hero story, one list of the rest. Generated pages use
the same header and cards via `sitegen.py` (`head()`, `mini_card()`). OG images use the same palette (OG_VERSION v4).
Old design (rollback only): `redesign/backup/pre-redesign.tgz` (see `redesign/README.md`).
