#!/usr/bin/env python3
"""STORIES — Instagram-style 24h "stories" for نبض فردا, refreshed every ~3 hours.

Two steps (like the nightly pipeline):

  (apply --deploy --telegram also posts kept stories flagged breaking to Telegram via telegram_post.py stories)
  update_stories.py fetch [--hours 3] [--max 8] [--min-score 3] [--include-today]
      Pull every feed in scripts/feeds.json (same code as fetch_news.py), keep items published in the last
      --hours that are NOT already in public/data/stories.json or today's day file, score them for
      "notability" (covered by several outlets, big launch/breach/lawsuit/etc., official AI-lab posts, HN
      front page...) and write the best ones to data/stories/pending.json with empty title_fa / summary_fa.
      --include-today also considers items of the latest day file (used for the first seed run).
      Prints CANDIDATES=N. If N == 0 → nothing to do (exit 0, do NOT deploy).

  (agent) edit data/stories/pending.json: for each candidate worth a story fill title_fa + summary_fa;
      set "drop": true (or leave title_fa empty) for anything not genuinely notable.

  update_stories.py apply [--deploy]
      Merge filled candidates into public/data/stories.json (added_at = now), drop stories older than 24h,
      keep the newest 15, verify the site still builds (build.py in a scratch copy + JSON/asset/JS checks),
      archive the pending file. Prints ADDED=N. With --deploy and N > 0 it runs scripts/deploy_cli.sh and
      checks the live stories.json. If N == 0 it only prunes locally and exits 0 without deploying
      (expired stories are also hidden client-side, so no deploy is needed just to expire them).

  update_stories.py status      show current stories and their age.
"""
import argparse, math, concurrent.futures as cf, json, re, shutil, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn  # noqa: E402  (reuse feed list + fetching/cleaning/categorizing code)

ROOT = fn.ROOT
PUB = ROOT / "public"
STORIES = PUB / "data/stories.json"
PENDING = ROOT / "data/stories/pending.json"
DONE_DIR = ROOT / "data/stories/applied"
LIVE = "https://nabz-farda.vercel.app"
TTL_H = 24
MAX_STORIES = 15

STOP = set("the and for with from that this into over after about your you are was were has have had its it's not but how why what when who will can new now just more than out off get got all one two say says said amid".split())
BREAKING = re.compile(r"\b(launch(es|ed)?|announc\w*|unveil\w*|introduc\w*|releas(e|es|ed)|debuts?|acquir\w*|acquisition|buys?|merger|sues?|sued|lawsuit|antitrust|fine[sd]?|ban(s|ned)?|breach\w*|hack(ed|ers?)?|leak(s|ed)?|outage|down|layoffs?|lays off|fired|resign\w*|steps down|ceo|ipo|raises|funding|valuation|billion|record|delay(s|ed)?|cancel\w*|shut(s|ting)? down|recall|price hike|exploit|vulnerability|zero-day|ransomware|gpt-?\d\S*|gemini \d|claude \d|llama \d|iphone \d+|pixel \d+|galaxy|ps5|ps6|switch 2|xbox|gta ?(6|vi)|half-life|elder scrolls|nintendo direct|state of play|showcase|first look|revealed?)\b", re.I)
SOFT = re.compile(r"\b(how to|review|reviewed|hands-on|podcast|guide|explained|opinion|interview|tips|everything we know|you should|i tried|i played|why i|ranking|ranked|best|vs\.?|versus|deal|week in|this week|recap|roundup|quiz|newsletter|sponsored|wordle|puzzle|answers?|hints?)\b", re.I)
BIG = re.compile(r"\b(openai|chatgpt|anthropic|claude|google|deepmind|gemini|apple|microsoft|meta|nvidia|amazon|tesla|spacex|musk|samsung|tsmc|intel|amd|sony|playstation|nintendo|xbox|valve|steam|epic|rockstar|ea|ubisoft|netflix|tiktok|x\.com|xai|grok|deepseek|mistral|qualcomm|arm|huawei)\b", re.I)
OFFICIAL = {"OpenAI", "Google AI", "Google DeepMind", "Hugging Face"}


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def ktokens(s):
    s = re.sub(r"[’']s\b", "", s.lower())
    return {w for w in re.findall(r"[a-z0-9]+", s) if (len(w) > 2 or w.isdigit()) and w not in STOP}


def jacc(a, b):
    return len(a & b) / max(1, len(a | b))


IDF = {}


def build_idf(titles):
    """idf over all fetched titles, so rare names (RuneScape, Shield) weigh more than common words."""
    import math
    df = {}
    for t in titles:
        for w in ktokens(t):
            df[w] = df.get(w, 0) + 1
    n = max(1, len(titles))
    IDF.clear()
    IDF.update({w: math.log((n + 1) / (c + 0.5)) for w, c in df.items()})
    IDF["__rare__"] = math.log((n + 1) / 4.5)  # idf of a word seen in <= 4 titles


def same_story(a, b, thr=0.2):
    """idf-weighted cosine similarity of two title token sets (>= thr -> same story)."""
    if not a or not b:
        return False
    shared = a & b
    rare = IDF.get("__rare__", 99)
    if len(shared) >= 2 and any(IDF.get(t, 99) >= rare for t in shared):
        return True  # e.g. "RuneScape 4 announced ..." vs "RuneScape 4 officially revealed"
    d = math.log(1000)
    w = lambda t: IDF.get(t, d) ** 2
    num = sum(w(t) for t in a & b)
    den = (sum(w(t) for t in a) * sum(w(t) for t in b)) ** 0.5
    return den > 0 and num / den >= thr


def load_stories():
    if not STORIES.exists():
        return []
    d = json.loads(STORIES.read_text())
    return d if isinstance(d, list) else d.get("stories", [])


def latest_day_items():
    out = []
    try:
        arch = json.loads((PUB / "data/archive.json").read_text())
        dates = {arch.get("latest"), now_utc().astimezone(fn.TEHRAN).strftime("%Y-%m-%d")}
    except Exception:
        dates = {now_utc().astimezone(fn.TEHRAN).strftime("%Y-%m-%d")}
    for d in dates:
        p = PUB / f"data/days/{d}.json"
        if d and p.exists():
            out += json.loads(p.read_text()).get("items", [])
    return out


def score(it, pool):
    """Heuristic notability score + human-readable reasons (the agent makes the final call)."""
    s, why = 0, []
    tk = ktokens(it["title"])
    others = {o["source"] for o in pool if o is not it and o["source"] != it["source"] and same_story(tk, o["_tk"])}
    if others:
        s += 3 * min(len(others), 3); why.append("also covered by " + ", ".join(sorted(others)))
    if BREAKING.search(it["title"]):
        s += 2; why.append("breaking keyword: " + BREAKING.search(it["title"]).group(0))
    if BIG.search(it["title"]):
        s += 1; why.append("major company/product: " + BIG.search(it["title"]).group(0))
    if it["source"] in OFFICIAL:
        s += 2; why.append("official announcement")
    if it["source"] == "Hacker News":
        s += 2; why.append("HN front page (100+ points)")
    if SOFT.search(it["title"]):
        s -= 3; why.append("soft/evergreen: " + SOFT.search(it["title"]).group(0))
    if not it.get("image"):
        s -= 1; why.append("no image")
    return s, why


def cmd_fetch(a):
    now = now_utc()
    feeds = fn.load_feeds()
    report, items = fn.collect(feeds)
    failed = [r for r in report if r["error"] or not r["entries"]]
    for r in failed:
        print(f"  WARN feed failed: {r['source']} {r['feed']} -> {r['error'] or 'no entries'}", file=sys.stderr)
    # same article listed by several feeds of one outlet -> keep one
    uniq = {}
    for it in sorted(items, key=lambda x: -x["_ts"]):
        uniq.setdefault(fn.norm_url(it["link"]), it)
    items = list(uniq.values())
    build_idf([i["title"] for i in items])
    for it in items:
        it["category"] = fn.categorize(it["feed_cat"], it["title"], it["summary"])
        it["_tk"] = ktokens(it["title"])
    # pool used to measure multi-outlet coverage: everything from the last 18h
    pool = [i for i in items if i["_ts"] >= (now - timedelta(hours=18)).timestamp()]

    existing = load_stories()
    day = latest_day_items()
    seen_ids = {s["id"] for s in existing} | {d["id"] for d in day}
    seen_urls = {fn.norm_url(s.get("url") or "") for s in existing} | {fn.norm_url(d.get("link") or "") for d in day}
    seen_tk = [ktokens(s.get("title") or "") for s in existing]
    day_tk = [ktokens(d.get("title") or "") for d in day]

    cutoff = (now - timedelta(hours=a.hours)).timestamp()
    fresh = [i for i in items if cutoff <= i["_ts"] <= now.timestamp() + 3600]
    if a.include_today:  # seed mode: today's day-file items are allowed as candidates too
        for d in day:
            fresh.append({"id": d["id"], "source": d["source"], "title": d["title"], "summary": "", "link": d["link"],
                          "image": d.get("image"), "published": d["published"], "category": d["category"],
                          "_ts": parse(d["published"]).timestamp(), "_day_fa": [d.get("title_fa"), d.get("summary_fa")]})
        for f in fresh:
            f.setdefault("_tk", ktokens(f["title"]))
        pool += [f for f in fresh if "_day_fa" in f]

    cands, taken = [], []
    for it in sorted(fresh, key=lambda x: -x["_ts"]):
        tk = ktokens(it["title"])
        if it["id"] in seen_ids and "_day_fa" not in it or fn.norm_url(it["link"]) in seen_urls and "_day_fa" not in it:
            continue
        if any(same_story(tk, t) for t in seen_tk + taken):          # same story already a story / candidate
            continue
        if "_day_fa" not in it and any(same_story(tk, t) for t in day_tk):   # already on today's page
            continue
        if it["id"] in {s["id"] for s in existing}:
            continue
        sc, why = score(it, pool)
        if sc < a.min_score:
            continue
        taken.append(tk)
        it["_score"], it["_why"] = sc, why
        cands.append(it)
    cands = sorted(cands, key=lambda x: (-x["_score"], -x["_ts"]))[: a.max]

    need = [c for c in cands if not c.get("image")]
    with cf.ThreadPoolExecutor(8) as ex:
        for c, img in zip(need, ex.map(lambda c: fn.og_image(c["link"]), need)):
            c["image"] = img
    for c in cands:
        if c.get("image"):
            c["image"] = re.sub(r"([?&])w=(\d{2,3})(?=&|$)", r"\1w=1200", c["image"])

    out = {"fetched_at": iso(now), "hours": a.hours, "instructions":
           "Fill title_fa + summary_fa (1–2 Persian sentences) for each candidate worth a story; set drop:true for the rest. Then run: update_stories.py apply --deploy",
           "candidates": [{
               "id": c["id"], "title_fa": "", "summary_fa": "", "drop": False,
               "category": c["category"], "source": c["source"], "url": c["link"], "image": c.get("image"),
               "published": c["published"], "_score": c["_score"], "_why": c["_why"],
               "_title": c["title"], "_summary": (c.get("summary") or "")[:400],
               **({"_day_fa": c["_day_fa"]} if c.get("_day_fa") else {}),
           } for c in cands]}
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    if not cands:
        PENDING.unlink(missing_ok=True)
        print(f"fetched {len(items)} items from {len(feeds) - len(failed)}/{len(feeds)} feeds; fresh={len(fresh)}")
        print("CANDIDATES=0  -> nothing notable; stop here (no apply, no deploy)")
        return
    PENDING.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"fetched {len(items)} items from {len(feeds) - len(failed)}/{len(feeds)} feeds; fresh={len(fresh)}")
    for c in out["candidates"]:
        print(f"  [{c['_score']:>2}] {c['id']} {c['category']:<4} {c['source']:<16} {c['_title'][:90]}")
    print(f"CANDIDATES={len(cands)}  -> fill title_fa/summary_fa in {PENDING.relative_to(ROOT)}, then: update_stories.py apply --deploy")


def is_breaking(c):
    """Telegram 'فوری' flag: the agent's explicit "breaking": true/false in pending.json wins; otherwise
    auto = score >= BREAKING_MIN and a breaking keyword (launch/breach/lawsuit/…) in the title."""
    if isinstance(c.get("breaking"), bool):
        return c["breaking"]
    return c.get("_score", 0) >= BREAKING_MIN and bool(BREAKING.search(c.get("_title", "")))


BREAKING_MIN = 6


def prune(stories, now):
    keep = [s for s in stories if now - parse(s["added_at"]) < timedelta(hours=TTL_H)]
    keep.sort(key=lambda s: (s["added_at"], s["published"]), reverse=True)
    return keep[:MAX_STORIES]


def check_site():
    """Make sure the main site still builds and the data files the page loads are valid."""
    errs = []
    arch = json.loads((PUB / "data/archive.json").read_text())
    latest = arch["latest"]
    day = json.loads((PUB / f"data/days/{latest}.json").read_text())
    if not day.get("items"):
        errs.append("latest day file has no items")
    st = json.loads(STORIES.read_text())
    assert isinstance(st, list)
    for s in st:
        for k in ("id", "title_fa", "summary_fa", "category", "source", "url", "published", "added_at"):
            if not s.get(k):
                errs.append(f"story {s.get('id')} missing {k}")
        if s.get("category") not in fn.CATS:
            errs.append(f"story {s.get('id')} bad category {s.get('category')}")
    html = (PUB / "index.html").read_text()
    for ref in re.findall(r'(?:src|href)="(/assets/[^"?]+)', html):
        if not (PUB / ref.lstrip("/")).exists():
            errs.append(f"missing asset {ref}")
    for item in day["items"][:3]:   # per-article pages + OG images from build.py/sitegen.py
        for rel in (f"news/{latest}/{item['id']}.html", f"og/{latest}/{item['id']}.png"):
            if not (PUB / rel).exists():
                errs.append(f"missing {rel} (run: .venv/bin/python scripts/build.py --pages-only)")
    for rel in ("sitemap.xml", "robots.txt", "feed.xml", "og/default.png"):
        if not (PUB / rel).exists():
            errs.append(f"missing {rel}")
    if 'id="stories"' not in html:
        errs.append("index.html lacks the stories bar container")
    if shutil.which("node"):
        for js in (PUB / "assets").glob("*.js"):
            r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
            if r.returncode:
                errs.append(f"JS syntax error in {js.name}: {r.stderr.strip()[:300]}")
    # run the real nightly build.py on a scratch copy (does not touch public/)
    if (ROOT / f"data/raw/{latest}.json").exists():
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            shutil.copytree(ROOT / "scripts", t / "scripts")
            shutil.copytree(ROOT / "data/raw", t / "data/raw")
            if (ROOT / "data/translations").exists():
                shutil.copytree(ROOT / "data/translations", t / "data/translations")
            shutil.copytree(PUB, t / "public", ignore=shutil.ignore_patterns(".vercel"))
            if (ROOT / "data/og-manifest.json").exists():   # lets sitegen skip redrawing unchanged OG images
                shutil.copy2(ROOT / "data/og-manifest.json", t / "data/og-manifest.json")
            r = subprocess.run([sys.executable, str(t / "scripts/build.py"), latest], capture_output=True, text=True)
            if r.returncode:
                errs.append("build.py failed: " + (r.stderr or r.stdout).strip()[:300])
            else:
                print("  build check:", r.stdout.strip())
    return errs


def cmd_apply(a):
    now = now_utc()
    stories = load_stories()
    added, dropped = [], 0
    if PENDING.exists():
        pend = json.loads(PENDING.read_text())
        have = {s["id"] for s in stories}
        for c in pend.get("candidates", []):
            tf, sf = (c.get("title_fa") or "").strip(), (c.get("summary_fa") or "").strip()
            if c.get("drop") or not tf or not sf or c["id"] in have:
                dropped += 1
                continue
            added.append({"id": c["id"], "title_fa": tf, "summary_fa": sf, "category": c["category"],
                          "source": c["source"], "url": c["url"], "image": c.get("image"),
                          "published": c["published"], "added_at": iso(now), "title": c.get("_title", ""),
                          "score": c.get("_score", 0), "breaking": is_breaking(c)})
        DONE_DIR.mkdir(parents=True, exist_ok=True)
        PENDING.rename(DONE_DIR / f"{now.astimezone(fn.TEHRAN).strftime('%Y-%m-%dT%H%M')}.json")
    else:
        print("no pending file (run fetch first) — pruning only")
    before = {s["id"] for s in stories}
    # newest additions first; stagger added_at by a second so the agent's order is kept
    for k, s in enumerate(added):
        s["added_at"] = iso(now - timedelta(seconds=k))
    merged = prune(added + stories, now)
    expired = len(before - {s["id"] for s in merged})
    STORIES.parent.mkdir(parents=True, exist_ok=True)
    STORIES.write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f"stories.json: {len(merged)} live stories (added {len(added)}, skipped {dropped}, expired/trimmed {expired})")
    errs = check_site()
    if errs:
        for e in errs:
            print("  ERROR", e)
        sys.exit("site check FAILED — fix before deploying")
    print("  site check OK")
    print(f"ADDED={len(added)}")
    if not added:
        print("nothing new -> no deploy")
        return
    if not a.deploy:
        print("NEXT: bash scripts/deploy_cli.sh   (or re-run with --deploy)")
        return
    r = subprocess.run(["bash", str(ROOT / "scripts/deploy_cli.sh")])
    if r.returncode:
        sys.exit("deploy FAILED (exit %d)" % r.returncode)
    verify_live({s["id"] for s in added})
    if a.telegram:   # brief "فوری" text posts for kept stories flagged breaking (never fails the stories run)
        r = subprocess.run([sys.executable, str(ROOT / "scripts/telegram_post.py"), "stories"])
        print("telegram: OK" if r.returncode == 0 else f"telegram: WARN exit {r.returncode} (stories are live anyway)")


def verify_live(ids):
    for attempt in range(6):
        try:
            req = urllib.request.Request(f"{LIVE}/data/stories.json?t={int(time.time())}", headers={"Cache-Control": "no-cache"})
            live = {s["id"] for s in json.loads(urllib.request.urlopen(req, timeout=20).read())}
            if ids <= live:
                print(f"LIVE OK: {LIVE} serves {len(live)} stories incl. all new ones")
                return
        except Exception as ex:
            print("  live check:", ex)
        time.sleep(5)
    sys.exit("LIVE CHECK FAILED: new stories not visible on " + LIVE)


def cmd_status(a):
    now = now_utc()
    for s in load_stories():
        age = (now - parse(s["added_at"])).total_seconds() / 3600
        print(f"{s['id']} {age:5.1f}h {'EXPIRED' if age >= TTL_H else '':7} {s['category']:<4} {s['source']:<16} {s['title_fa']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--hours", type=float, default=3)
    f.add_argument("--max", type=int, default=8)
    f.add_argument("--min-score", type=int, default=3)
    f.add_argument("--include-today", action="store_true")
    p = sub.add_parser("apply")
    p.add_argument("--deploy", action="store_true")
    p.add_argument("--telegram", action="store_true", help="after a successful deploy, post breaking stories to the channel")
    sub.add_parser("status")
    a = ap.parse_args()
    {"fetch": cmd_fetch, "apply": cmd_apply, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
