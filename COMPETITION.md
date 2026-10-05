# Nabz-e Farda — Competition showcase

**Live:** https://nabz-farda.vercel.app  
**Repo:** https://github.com/yasinfallahati/nabz-farda (private)  
**Presentation notes:** [`docs/PRESENTATION.md`](docs/PRESENTATION.md)  
**One-pager:** [`docs/contest/nabz-farda-onepager.png`](docs/contest/nabz-farda-onepager.png)

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
| Search | Client-side filter over `/data/search-index.json` + homepage chips |
| PWA shell | Manifest + lightweight service worker + Persian offline page |
| Article UX | Reading time, copy/Telegram/X share (no tracking SDKs), related articles, خلاصه + خبر کامل |

Internal JSON under `/data/` powers search and the ops dashboard; there is **no public `/api/` product surface**. The automation dashboard is **unlisted** in main nav/footer — reach it from `/about/` (judges) or directly at https://nabz-farda.vercel.app/automation/.

## Judge walkthrough (≈5 minutes)

1. **Home** — https://nabz-farda.vercel.app — RTL layout, stories bar, category chips, search.  
2. **About (judges)** — https://nabz-farda.vercel.app/about/ — architecture + schedule; link to automation dashboard.  
3. **Automation (unlisted)** — https://nabz-farda.vercel.app/automation/ — pipeline stages + live ops stats (also linked from About).  
4. **Article** — open any card; check خلاصه / خبر کامل, reading time, share, related.  
5. **Search / PWA** — `/search/`; optionally “Add to Home Screen”.

## How to demo live (no credentials needed)

```bash
curl -s https://nabz-farda.vercel.app/data/ops.json | head
curl -s https://nabz-farda.vercel.app/data/search-index.json | head
```

Nightly rebuild (operators): see `NIGHTLY.md`. Stories: `scripts/update_stories.py`.

## Constraints honored

- Free/open tooling only (no new paid APIs)
- Static deploy only
- Persian-first UI, dark heartbeat aesthetic
- Existing `summary_fa` / `body_fa` behavior preserved
