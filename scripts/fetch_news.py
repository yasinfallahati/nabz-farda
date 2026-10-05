#!/usr/bin/env python3
"""Step 1 — FETCH: pull RSS feeds, dedupe, categorize, select top items per category.

Output: data/raw/<YYYY-MM-DD>.json  (date = Tehran date of the run)
Usage:  .venv/bin/python scripts/fetch_news.py [--date YYYY-MM-DD] [--hours 30] [--per-cat 12]
"""
import argparse, calendar, concurrent.futures as cf, hashlib, html, json, re, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import feedparser, requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
TEHRAN = timezone(timedelta(hours=3, minutes=30))  # Iran has no DST since 2022
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 NabzFardaBot/1.0"}
CATS = ["ai", "game", "tech"]

AI_KW = r"\b(ai|a\.i\.|artificial intelligence|openai|chatgpt|gpt-?\d|llm|llms|gemini|claude|anthropic|deepmind|copilot|machine learning|neural|generative|genai|chatbot|agentic|ai agents?|mistral|llama|grok|xai|nvidia h\d+|deepseek|hugging face|diffusion model|sora|midjourney|perplexity)\b"
GAME_KW = r"\b(game|games|gaming|gamer|playstation|ps5|ps6|xbox|nintendo|switch 2|steam|esports|e-sports|fortnite|minecraft|zelda|mario|pokemon|pokémon|gta|call of duty|valve|ubisoft|ea sports|bethesda|blizzard|riot games|capcom|square enix|indie game|rpg|fps)\b"
TECH_KW = r"\b(apple|iphone|ipad|mac|google|android|pixel|samsung|microsoft|windows|linux|meta|amazon|tesla|spacex|chip|chips|cpu|gpu|intel|amd|nvidia|qualcomm|tsmc|software|hardware|app|apps|startup|security|hack|hacker|privacy|browser|chrome|firefox|cloud|data|robot|robotics|quantum|ev|battery|smartphone|laptop|open source|programming|rust|python|javascript|developer|api|internet|crypto|semiconductor|5g|satellite|server|kernel|database|code|compiler|github)\b"


SKIP_RE = re.compile(r"\b(deals?|sale|coupons?|discount|promo code|% off|prime day|best .* to buy|gift guide|sponsored|wordle|connections hint|nyt connections|quordle|crossword)\b", re.I)


def norm_url(u):
    p = urlsplit(u.strip())
    return urlunsplit((p.scheme, p.netloc.lower().replace("www.", ""), p.path.rstrip("/"), "", ""))


def clean_text(s, n=400):
    if not s:
        return ""
    t = BeautifulSoup(s, "html.parser").get_text(" ", strip=True)
    t = html.unescape(re.sub(r"\s+", " ", t)).strip()
    t = re.sub(r"(Article URL|Comments URL|Points|# Comments):.*$", "", t).strip()
    t = re.sub(r"The post .* appeared first on .*\.?$", "", t).strip()
    return (t[: n - 1] + "…") if len(t) > n else t


def find_image(e):
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key) or []:
            u = m.get("url")
            if u and not u.endswith(".mp4"):
                return u
    for l in e.get("links", []):
        if l.get("type", "").startswith("image") and l.get("href"):
            return l["href"]
    for blob in [e.get("summary", "")] + [c.get("value", "") for c in e.get("content", []) or []]:
        m = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", blob or "")
        if m and m.group(1).startswith("http"):
            return html.unescape(m.group(1))
    return None


def og_image(url):
    try:
        r = requests.get(url, headers=UA, timeout=8)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return None
        s = BeautifulSoup(r.text[:400000], "html.parser")
        for attrs in ({"property": "og:image"}, {"name": "og:image"}, {"name": "twitter:image"}, {"property": "twitter:image"}):
            t = s.find("meta", attrs=attrs)
            if t and t.get("content", "").startswith("http"):
                return t["content"]
    except Exception:
        return None
    return None


def categorize(feed_cat, title, summary):
    text = f"{title} {summary}".lower()
    t = title.lower()
    ai = len(re.findall(AI_KW, t)) * 2 + len(re.findall(AI_KW, text))
    game = len(re.findall(GAME_KW, t)) * 2 + len(re.findall(GAME_KW, text))
    if feed_cat == "game":
        return "game"
    if feed_cat == "ai":
        return "ai"
    # general tech feeds: promote to AI / game when clearly about it (title-driven)
    if re.search(AI_KW, t) and ai >= 2:
        return "ai"
    if re.search(GAME_KW, t) and game >= 3:
        return "game"
    return "tech"


def fetch_feed(f):
    err = None
    for attempt in range(3):
        try:
            r = requests.get(f["url"], headers=UA, timeout=20)
            r.raise_for_status()
            return f, feedparser.parse(r.content).entries, None
        except Exception as ex:
            err = str(ex)
            time.sleep(2 + attempt * 3)
    return f, [], err


def tokens(s):
    return set(w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2)


def collect(feeds):
    """Fetch all feeds -> (report, items). Shared with update_stories.py."""
    with cf.ThreadPoolExecutor(12) as ex:
        results = list(ex.map(fetch_feed, feeds))

    report, items = [], []
    for f, entries, err in results:
        report.append({"feed": f["url"], "source": f["name"], "entries": len(entries), "error": err})
        for e in entries[:60]:
            link = e.get("link")
            title = clean_text(e.get("title"), 220)
            pp = e.get("published_parsed") or e.get("updated_parsed")
            if not link or not title or not pp:
                continue
            ts = datetime.fromtimestamp(calendar.timegm(pp), timezone.utc)
            summary = clean_text(e.get("summary") or (e.get("content") or [{}])[0].get("value", ""), 450)
            if SKIP_RE.search(title):
                continue
            if f.get("require_keywords") and not re.search(f"{AI_KW}|{GAME_KW}|{TECH_KW}", title.lower()):
                continue
            items.append({
                "id": hashlib.sha1(norm_url(link).encode()).hexdigest()[:10],
                "source": f["name"], "feed_cat": f["cat"], "feed_max": f.get("max"),
                "title": title, "summary": summary, "link": link,
                "comments": e.get("comments") if f["name"] == "Hacker News" else None,
                "image": find_image(e), "published": ts.isoformat(),
                "_ts": ts.timestamp(),
            })
    return report, items


def load_feeds():
    return json.loads((ROOT / "scripts/feeds.json").read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="Tehran date label (default: today in Tehran)")
    ap.add_argument("--hours", type=float, default=30, help="freshness window")
    ap.add_argument("--per-cat", type=int, default=12)
    ap.add_argument("--max-per-source", type=int, default=3)
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    date = a.date or now.astimezone(TEHRAN).strftime("%Y-%m-%d")
    feeds = load_feeds()

    report, items = collect(feeds)

    # dedupe by url, then by near-identical titles
    seen, uniq = {}, []
    for it in sorted(items, key=lambda x: -x["_ts"]):
        k = norm_url(it["link"])
        if k in seen:
            continue
        tk = tokens(it["title"])
        if any(len(tk & u["_tk"]) / max(1, len(tk | u["_tk"])) > 0.6 for u in uniq):
            continue
        seen[k] = 1
        it["_tk"] = tk
        uniq.append(it)

    for it in uniq:
        it["category"] = categorize(it["feed_cat"], it["title"], it["summary"])

    # select per category: fresh window, round-robin over sources for diversity
    selected = []
    for cat in CATS:
        pool = [i for i in uniq if i["category"] == cat]
        hours = a.hours
        fresh = []
        while hours <= 24 * 7:
            cutoff = (now - timedelta(hours=hours)).timestamp()
            fresh = [i for i in pool if i["_ts"] >= cutoff and i["_ts"] <= now.timestamp() + 3600]
            if len(fresh) >= a.per_cat:
                break
            hours *= 2
        by_src = {}
        for i in sorted(fresh, key=lambda x: -x["_ts"]):
            by_src.setdefault(i["source"], []).append(i)
        picked, rnd = [], 0
        while len(picked) < a.per_cat and any(by_src.values()):
            for s in list(by_src):
                lim = min(a.max_per_source, next((f.get("max") for f in feeds if f["name"] == s and f.get("max")), 99))
                if by_src[s] and rnd < lim and len(picked) < a.per_cat:
                    picked.append(by_src[s].pop(0))
            rnd += 1
            if rnd > a.max_per_source:
                break
        selected += sorted(picked, key=lambda x: -x["_ts"])

    # fill missing images via og:image (only for selected items)
    need = [i for i in selected if not i["image"]]
    with cf.ThreadPoolExecutor(10) as ex:
        for i, img in zip(need, ex.map(lambda i: og_image(i["link"]), need)):
            i["image"] = img

    for i in selected:  # upgrade known low-res thumbnail URLs
        if i["image"]:
            i["image"] = re.sub(r"([?&])w=(\d{2,3})(?=&|$)", r"\1w=1200", i["image"])
    out = []
    for i in selected:
        out.append({k: v for k, v in i.items() if not k.startswith("_") and k not in ("feed_cat", "feed_max")} | {"title_fa": "", "summary_fa": ""})

    data = {
        "date": date,
        "fetched_at": now.isoformat(),
        "counts": {c: sum(1 for i in out if i["category"] == c) for c in CATS},
        "feeds": report,
        "items": out,
    }
    p = ROOT / "data/raw" / f"{date}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    bad = [r for r in report if r["error"] or not r["entries"]]
    print(f"wrote {p}  items={len(out)} counts={data['counts']}  images={sum(1 for i in out if i['image'])}/{len(out)}")
    for r in bad:
        print(f"  WARN feed failed: {r['source']} {r['feed']} -> {r['error'] or 'no entries'}", file=sys.stderr)


if __name__ == "__main__":
    main()
