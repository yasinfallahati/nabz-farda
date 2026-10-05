#!/usr/bin/env python3
"""Step 3 — BUILD: merge raw + translations -> public/data/days/DATE.json, regenerate public/data/archive.json.

Usage: build.py [DATE] [--allow-missing]      build DATE from data/raw + data/translations, then regenerate pages
       build.py --pages-only                    only regenerate pages/OG/sitemap/feed from public/data/days/*.json
After the data files, scripts/sitegen.py regenerates the static SEO layer for ALL days: per-story pages
(public/news/DATE/ID.html), day pages, OG images (public/og/), sitemap.xml, sitemap-news.xml, robots.txt, feed.xml.
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"


def main():
    sys.path.insert(0, str(ROOT / "scripts"))
    import sitegen
    if "--pages-only" in sys.argv:
        print(sitegen.generate()); return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    allow = "--allow-missing" in sys.argv
    date = args[0] if args else sorted((ROOT / "data/raw").glob("*.json"))[-1].stem
    raw = json.loads((ROOT / f"data/raw/{date}.json").read_text())
    tp = ROOT / f"data/translations/{date}.json"
    tr = json.loads(tp.read_text()) if tp.exists() else {}
    items, missing = [], []
    for it in raw["items"]:
        t = tr.get(it["id"], {})
        if t.get("drop"):
            continue
        if not (t.get("title_fa") and t.get("summary_fa")):
            missing.append(it["id"])
        items.append({
            "id": it["id"], "category": it["category"], "source": it["source"],
            "title": it["title"], "title_fa": (t.get("title_fa") or "").strip(),
            "summary_fa": (t.get("summary_fa") or "").strip(),
            "link": it["link"], "image": it.get("image"), "published": it["published"], "page": f"/news/{date}/{it['id']}",
            **({"featured": True} if t.get("featured") else {}),
        })
    if missing and not allow:
        sys.exit(f"ERROR: {len(missing)} items lack Persian text (run translate.py check {date}); use --allow-missing to build anyway")
    items.sort(key=lambda x: x["published"], reverse=True)
    day = {"date": date, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "fetched_at": raw.get("fetched_at"), "items": items}
    (PUB / "data/days").mkdir(parents=True, exist_ok=True)
    (PUB / f"data/days/{date}.json").write_text(json.dumps(day, ensure_ascii=False, separators=(",", ":")))
    days = []
    for f in sorted((PUB / "data/days").glob("*.json"), reverse=True):
        d = json.loads(f.read_text())
        days.append({"date": d["date"], "count": len(d["items"]), "updated_at": d["updated_at"]})
    (PUB / "data/archive.json").write_text(json.dumps({"latest": days[0]["date"], "days": days}, ensure_ascii=False, separators=(",", ":")))
    print(f"built {date}: {len(items)} items ({len(missing)} untranslated); archive has {len(days)} day(s)")
    print(sitegen.generate())


if __name__ == "__main__":
    main()