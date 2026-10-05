# نبض فردا — Nabz-e Farda

**Live:** https://nabz-farda.vercel.app

## فارسی

«نبض فردا» یک سایت خبری فارسی و استاتیک دربارهٔ **هوش مصنوعی، تکنولوژی و گیم** است. هر شب خبرها از فیدهای RSS
جمع‌آوری، به فارسی ترجمه و خلاصه، و سایت بازسازی و روی Vercel منتشر می‌شود. یک نوار «استوری» هر چند ساعت با
خبرهای مهم به‌روز می‌شود و منتخب خبرها در کانال تلگرام نبض فردا پست می‌شوند. پوشهٔ `insta/` اسکریپت‌های ساخت
ریلز، کاروسل و استوری اینستاگرام است.

### ساختار
| مسیر | توضیح |
|---|---|
| `public/` | خود سایت استاتیک (همین پوشه روی Vercel دیپلوی می‌شود): `index.html`، `assets/`، `data/`، صفحات `news/`، تصاویر `og/`، sitemap و feed |
| `scripts/` | پایپ‌لاین: `fetch_news.py` → `translate.py` → `build.py` + `sitegen.py`، `update_stories.py`، `telegram_post.py`، اسکریپت‌های دیپلوی |
| `config/telegram.json` | فقط شناسهٔ کانال/مالک تلگرام (بدون توکن) |
| `data/` | خبرهای خام، فایل‌های ترجمه، آرشیو استوری‌ها، وضعیت پست‌های تلگرام |
| `deploy/` | خروجی‌های موقت دیپلوی (`payload.json`, `state.json`) — در گیت نیستند |
| `redesign/` | یادداشت طراحی جدید |
| `insta/` | تولیدکنندهٔ ریلز/استوری/کاروسل اینستاگرام (کد، spec ها، کپشن‌ها، فونت Vazirmatn) |
| `NIGHTLY.md` | دستورالعمل کامل اجرای شبانه |

### اجرای شبانه (خلاصهٔ NIGHTLY.md)
هر شب ساعت ۰۰:۰۰ به وقت تهران:
1. `scripts/nightly_prepare.sh DATE` — دریافت فیدها و ساخت فایل ترجمه
2. پر کردن `title_fa` و `summary_fa` در `data/translations/DATE.json` (توسط عامل هوش مصنوعی)
3. `scripts/nightly_finish.sh DATE` — بررسی ترجمه، ساخت سایت، صفحات، تصاویر OG، sitemap و feed
4. دیپلوی: `bash scripts/deploy_cli.sh` (Vercel CLI با `VERCEL_TOKEN`) یا از طریق Vercel MCP با `deploy/payload.json`
5. بررسی سایت زنده
6. `scripts/telegram_post.py nightly DATE` — ارسال حدود ۸ خبر منتخب به تلگرام

استوری‌ها هر ۳ ساعت: `scripts/update_stories.py fetch` و سپس `apply --deploy --telegram`.

### متغیرهای محیطی
- `VERCEL_TOKEN` — برای دیپلوی با Vercel CLI
- `TELEGRAM_BOT_TOKEN` — برای ارسال پست به کانال تلگرام
- `NF_FONTS` (اختیاری) — مسیر فونت‌های Vazirmatn برای تصاویر OG (پیش‌فرض: `/workspace/insta/assets/fonts`؛ در این مخزن: `insta/assets/fonts`)

هیچ توکن یا رازی در این مخزن نیست.

---

## English

**Nabz-e Farda** ("Tomorrow's Pulse") is a static Persian-language news site covering **AI, tech and gaming**.
Every night, stories are fetched from RSS feeds, translated/summarized into Persian, and the site is rebuilt and
deployed to Vercel. An Instagram-style "stories" bar is refreshed every 3 hours with breaking items, and selected
stories are posted to the Nabz-e Farda Telegram channel. `insta/` holds the Instagram reel/carousel/story generators.

### Structure
| Path | What |
|---|---|
| `public/` | The static site — this is the folder deployed to Vercel (`index.html`, `assets/`, `data/`, generated `news/` pages, `og/` images, sitemaps, RSS feed) |
| `scripts/` | Pipeline: `fetch_news.py` → `translate.py` → `build.py` + `sitegen.py`; `update_stories.py`, `telegram_post.py`, deploy helpers |
| `config/telegram.json` | Telegram channel/owner chat ids only (no token) |
| `data/` | Raw fetched items, translation files, applied stories, Telegram posted-state |
| `deploy/` | Transient deploy artifacts (`payload.json`, `state.json`) — git-ignored |
| `redesign/` | Notes on the current design |
| `insta/` | Instagram reel/story/carousel generators (code, specs, captions, Vazirmatn fonts) |
| `NIGHTLY.md` | Full nightly runbook |

### Nightly build & deploy (see NIGHTLY.md)
Runs at 00:00 Asia/Tehran:
1. `scripts/nightly_prepare.sh DATE` — fetch feeds, export translation file
2. Fill `title_fa` / `summary_fa` in `data/translations/DATE.json` (done by the AI agent)
3. `scripts/nightly_finish.sh DATE` — check translations, build day data, article pages, OG images, sitemaps, feed
4. Deploy: `bash scripts/deploy_cli.sh` (Vercel CLI, `$VERCEL_TOKEN`) — or via the Vercel MCP `create_deployment` with `deploy/payload.json`
5. Verify the live site
6. `scripts/telegram_post.py nightly DATE` — post ~8 picks to Telegram

Stories (every 3 h): `scripts/update_stories.py fetch`, then `apply --deploy --telegram`.

Setup: `python3 -m venv .venv && .venv/bin/pip install feedparser requests beautifulsoup4 pillow`.
`public/.vercel/` is not committed; run `npx vercel link` inside `public/` (project `nabz-farda`) before using `deploy_cli.sh`.

### Environment variables
- `VERCEL_TOKEN` — Vercel CLI deploys
- `TELEGRAM_BOT_TOKEN` — Telegram channel posts
- `NF_FONTS` (optional) — Vazirmatn font dir for OG images (default `/workspace/insta/assets/fonts`; in this repo: `insta/assets/fonts`)

No tokens or secrets are stored in this repository.

### Not included
Python venv, rendered media (insta mp4/png/jpg, frames, QC images, zips), screenshots, backups (`*.tgz`, `*.pre-*`),
deploy state/payload, and the Vercel link file.
