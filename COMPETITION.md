# Nabz-e Farda — Competition showcase

**Live:** https://nabz-farda.vercel.app  
**Repo:** https://github.com/yasinfallahati/nabz-farda (private)

## What it is

Nabz-e Farda (“Tomorrow’s Pulse”) is a **fully static**, Persian-language automation news system for AI, technology, and gaming. There is **no application server and no database**. The `public/` folder *is* the site and deploys as-is to Vercel.

## Architecture (one sentence)

~26 English RSS feeds → nightly fetch/dedupe/categorize → Persian headline + summary + body → static HTML + OG images + sitemaps/RSS → Vercel → Telegram + Instagram assets; a lighter stories pass every 3 hours.

## Differentiators

| Capability | Why it matters |
|---|---|
| Static-only hosting | Fast, cheap, auditable; judges can curl every artifact |
| Dual cadence | Full edition at 00:00 Asia/Tehran + stories bar every 3h |
| Multi-channel | Web, Telegram posts, Instagram reel/carousel/stories from the same day data |
| SEO layer | Per-article pages, JSON-LD, Google News sitemap, RSS, OG cards with correct Persian shaping |
| Ops dashboard | `/automation/` reads live `ops.json` (counts, stories, telegram, commit, build time) |
| Public API | `/api/v1/latest.json`, `archive.json`, `ops.json`, `openapi.json` |
| Search | Client-side filter over `/data/search-index.json` + homepage chips |
| PWA shell | Manifest + lightweight service worker + Persian offline page |
| Article UX | Reading time, copy/Telegram/X share (no tracking SDKs), related articles, خلاصه + خبر کامل |

## Judge walkthrough (≈5 minutes)

1. **Home** — https://nabz-farda.vercel.app — RTL layout, stories bar, category chips, search.  
2. **Automation** — https://nabz-farda.vercel.app/automation/ — pipeline stages + live ops stats.  
3. **Article** — open any card; check خلاصه / خبر کامل, reading time, share, related.  
4. **API** — https://nabz-farda.vercel.app/api/ and curl `/api/v1/latest.json`.  
5. **About / Search / PWA** — `/about/`, `/search/`; optionally “Add to Home Screen”.

## How to demo live (no credentials needed)

```bash
curl -s https://nabz-farda.vercel.app/api/v1/ops.json | head
curl -s https://nabz-farda.vercel.app/api/v1/latest.json | head
curl -s https://nabz-farda.vercel.app/data/search-index.json | head
```

Nightly rebuild (operators): see `NIGHTLY.md`. Stories: `scripts/update_stories.py`.

## Constraints honored

- Free/open tooling only (no new paid APIs)
- Static deploy only
- Persian-first UI, dark heartbeat aesthetic
- Existing `summary_fa` / `body_fa` behavior preserved
