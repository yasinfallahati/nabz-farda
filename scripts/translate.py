#!/usr/bin/env python3
"""Step 2 — TRANSLATE helper (the translation itself is written by the nightly AI agent).

  translate.py export [DATE]  -> creates/refreshes data/translations/DATE.json with one entry per item:
        {"<id>": {"title_fa": "", "summary_fa": "", "body_fa": "", "featured": false, "drop": false,
                  "_source": "...", "_title": "...", "_summary": "..."}}
     The agent fills title_fa (natural Persian headline), summary_fa (1–2 Persian sentences),
     and body_fa (longer Persian write-up: ~3–6 short paragraphs / ~150–400 words, blank-line separated).
     Optional: "featured": true on ONE item to force it as the hero story; "drop": true to exclude an item
     (duplicate story, off-topic, ad/deal post). Fields starting with "_" are context only.
  translate.py check [DATE]   -> lists items still missing Persian text (exit 1 if any).
DATE defaults to the newest file in data/raw/.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def latest_date():
    files = sorted((ROOT / "data/raw").glob("*.json"))
    if not files:
        sys.exit("no raw data; run fetch_news.py first")
    return files[-1].stem


def is_translated(t):
    return bool(t.get("title_fa") and t.get("summary_fa") and t.get("body_fa"))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    date = sys.argv[2] if len(sys.argv) > 2 else latest_date()
    raw = json.loads((ROOT / f"data/raw/{date}.json").read_text())
    tp = ROOT / f"data/translations/{date}.json"
    tr = json.loads(tp.read_text()) if tp.exists() else {}
    if cmd == "export":
        out = {}
        for it in raw["items"]:
            old = tr.get(it["id"], {})
            out[it["id"]] = {
                "title_fa": old.get("title_fa", ""), "summary_fa": old.get("summary_fa", ""),
                "body_fa": old.get("body_fa", ""),
                "featured": old.get("featured", False), "drop": old.get("drop", False),
                "_cat": it["category"], "_source": it["source"], "_title": it["title"], "_summary": it["summary"][:350],
            }
        tp.write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print(f"wrote {tp} ({len(out)} items). Fill title_fa + summary_fa + body_fa for every item, then run: translate.py check {date}")
    elif cmd == "check":
        missing = [i for i in raw["items"] if not tr.get(i["id"], {}).get("drop")
                   and not is_translated(tr.get(i["id"], {}))]
        for i in missing:
            t = tr.get(i["id"], {})
            need = [f for f in ("title_fa", "summary_fa", "body_fa") if not t.get(f)]
            print(f"MISSING {i['id']}  [{i['source']}] need={need}  {i['title']}")
        print(f"{len(raw['items']) - len(missing)}/{len(raw['items'])} translated")
        sys.exit(1 if missing else 0)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
