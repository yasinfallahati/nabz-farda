#!/usr/bin/env python3
"""Post نبض فردا stories to the Telegram channel (bot token: env TELEGRAM_BOT_TOKEN, chat: config/telegram.json).

  telegram_post.py nightly [DATE] [--max 8] [--limit N] [--id ID ...] [--exclude ID ...] [--dry-run] [--no-verify]
      After the nightly build + deploy + verify: pick the ~8 best stories of DATE (default: latest day in archive),
      varied categories, skip ids already posted, and send each as a photo (its OG image) with an HTML caption:
      bold title, short summary, category hashtag, link to /news/DATE/ID. Checks each article page + OG image is
      live first (--no-verify skips). --limit N caps how many are actually sent this run (e.g. a test with 1).
  telegram_post.py stories [--max 3] [--hours 6] [--dry-run]
      Brief text posts for NEW story-bar items flagged "breaking": true in public/data/stories.json
      (set by update_stories.py apply), added within --hours, not yet posted. Called by `update_stories.py apply --telegram`.
  telegram_post.py status        show what has been posted

State: data/telegram/posted.json  {id: {kind, date, at, message_id}}  — an id is never posted twice.
Exit code: 0 ok (incl. nothing to post), 1 if any send failed (the rest are still attempted).
The token is never printed (it is scrubbed from any error text).
"""
import argparse, fcntl, json, os, re, sys, time
from datetime import datetime, timedelta, timezone
from html import escape as _esc
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
SITE = os.environ.get("SITE_URL", "https://nabz-farda.vercel.app").rstrip("/")
CFG = json.loads((ROOT / "config/telegram.json").read_text())
STATE = ROOT / "data/telegram/posted.json"
LOCK = ROOT / "data/telegram/.lock"
PAUSE = 1.6  # seconds between sends (Telegram allows ~20 msgs/min per channel)
CATS = {"ai": ("هوش مصنوعی", "#هوش_مصنوعی", "🤖"), "tech": ("تکنولوژی", "#تکنولوژی", "💻"), "game": ("گیم", "#گیم", "🎮")}
ORDER = ["ai", "tech", "game"]
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def escape(s):  # Telegram HTML: only &lt; &gt; &amp; &quot; are needed
    return _esc(str(s), quote=False).replace('"', "&quot;")


def scrub(s):
    s = str(s)
    return s.replace(TOKEN, "***") if TOKEN else s


def now_utc():
    return datetime.now(timezone.utc)


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    tmp.replace(STATE)


def tg(method, data=None, files=None, tries=4):
    """Call the Bot API; retries on 429 (retry_after) and network/5xx errors. Returns result or raises RuntimeError."""
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    last = None
    for k in range(tries):
        try:
            r = requests.post(url, data=data, files=files, timeout=40)
            j = r.json()
        except Exception as ex:
            last = f"network: {scrub(ex)}"; time.sleep(3 * (k + 1)); continue
        if j.get("ok"):
            return j["result"]
        ra = (j.get("parameters") or {}).get("retry_after")
        last = f"{j.get('error_code')} {scrub(j.get('description'))}"
        if ra:
            time.sleep(int(ra) + 1); continue
        if j.get("error_code", 0) >= 500:
            time.sleep(3 * (k + 1)); continue
        break  # 4xx: not retryable
    raise RuntimeError(last)


def cut(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def caption(it, page):
    name, tag, emo = CATS.get(it["category"], CATS["tech"])
    head = f"<b>{escape(it['title_fa'])}</b>"
    foot = (f"{emo} {tag} #نبض_فردا\n"
            f"🔗 <a href=\"{escape(page)}\">ادامهٔ خبر در نبض فردا</a> · منبع: {escape(it['source'])}")
    room = 1000 - len(head) - len(foot) - 8   # Telegram caption limit is 1024 chars (after entity parsing)
    return f"{head}\n\n{escape(cut(it.get('summary_fa'), room))}\n\n{foot}"


def is_live(url):
    try:
        return requests.head(url, timeout=20, allow_redirects=True).status_code == 200
    except Exception:
        return False


def pick(items, n):
    """Best n stories with varied categories: featured first, then round-robin over categories by notability score."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import update_stories as us
        us.build_idf([i["title"] for i in items])
        for i in items:
            i["_tk"] = us.ktokens(i["title"])
        sc = {i["id"]: us.score(i, items)[0] for i in items}
    except Exception as ex:  # scoring is a nicety; fall back to recency
        print("  WARN scoring unavailable:", ex)
        sc = {i["id"]: 0 for i in items}
    key = lambda i: (-(100 if i.get("featured") else 0) - sc[i["id"]] - (0 if i.get("image") else -1), i["published"])
    queues = {c: sorted([i for i in items if i["category"] == c], key=key) for c in ORDER}
    queues["_other"] = sorted([i for i in items if i["category"] not in ORDER], key=key)
    first = min(items, key=key) if items else None
    out = [first] if first else []
    rot = ORDER[:]
    if first and first["category"] in rot:   # continue the rotation after the lead story's category
        i = rot.index(first["category"]); rot = rot[i + 1:] + rot[: i + 1]
    while len(out) < n and any(queues.values()):
        for c in rot + ["_other"]:
            q = [i for i in queues[c] if i not in out]
            queues[c] = q
            if q and len(out) < n:
                out.append(q.pop(0)); queues[c] = q
    for i in items:
        i.pop("_tk", None)
    return out, sc


def cmd_nightly(a):
    arch = json.loads((PUB / "data/archive.json").read_text())
    date = a.date or arch["latest"]
    day = json.loads((PUB / f"data/days/{date}.json").read_text())
    st = load_state()
    items = [i for i in day["items"] if i.get("title_fa") and i.get("summary_fa")]
    if a.id:
        sel, sc = [i for i in items if i["id"] in a.id], {}
    else:
        sel, sc = pick([i for i in items if i["id"] not in st and i["id"] not in (a.exclude or [])], a.max)
    sel = [i for i in sel if i["id"] not in st]
    print(f"{date}: {len(items)} stories, {sum(1 for i in items if i['id'] in st)} already posted, selected {len(sel)}"
          + (f", sending at most {a.limit}" if a.limit is not None else ""))
    if a.limit is not None:
        sel = sel[: a.limit]
    fails = 0
    for k, it in enumerate(sel):
        page = f"{SITE}/news/{date}/{it['id']}"
        og = f"{SITE}/og/{date}/{it['id']}.png"
        cap = caption(it, page)
        print(f"- [{it['category']}] {it['id']} score={sc.get(it['id'], '-')} {it['title_fa'][:70]}")
        if a.dry_run:
            print("  " + cap.replace("\n", "\n  ")); continue
        if not a.no_verify and not (is_live(page) and is_live(og)):
            print("  SKIP: article page / OG image not live yet (deploy first)"); fails += 1; continue
        kb = json.dumps({"inline_keyboard": [[{"text": "📖 مطالعه در نبض فردا", "url": page}],
                                             [{"text": f"منبع اصلی: {it['source']}", "url": it["link"]}]]}, ensure_ascii=False)
        base = {"chat_id": CFG["chat_id"], "caption": cap, "parse_mode": "HTML", "reply_markup": kb}
        res, err = None, None
        local = PUB / f"og/{date}/{it['id']}.png"
        for how in ("og_url", "og_upload", "story_image", "text"):
            try:
                if how == "og_url":
                    res = tg("sendPhoto", {**base, "photo": og + f"?v={int(time.time() // 86400)}"})
                elif how == "og_upload" and local.exists():
                    with local.open("rb") as fh:
                        res = tg("sendPhoto", base, files={"photo": (local.name, fh, "image/png")})
                elif how == "story_image" and it.get("image"):
                    res = tg("sendPhoto", {**base, "photo": it["image"]})
                elif how == "text":
                    res = tg("sendMessage", {"chat_id": CFG["chat_id"], "text": cap, "parse_mode": "HTML", "reply_markup": kb})
                if res:
                    break
            except RuntimeError as ex:
                err = ex; print(f"  WARN {how} failed: {ex}")
        if not res:
            print(f"  FAILED: {err}"); fails += 1; continue
        st[it["id"]] = {"kind": "article", "date": date, "at": now_utc().isoformat(timespec="seconds"),
                        "message_id": res["message_id"], "via": how}
        save_state(st)
        print(f"  OK message_id={res['message_id']} via {how}")
        if k < len(sel) - 1:
            time.sleep(PAUSE)
    print(f"POSTED={0 if a.dry_run else len(sel) - fails} FAILED={fails}" + (" (dry run)" if a.dry_run else ""))
    return 1 if fails else 0


def cmd_stories(a):
    st = load_state()
    stories = json.loads((PUB / "data/stories.json").read_text())
    now = now_utc()
    new = [s for s in stories if s.get("breaking") and s["id"] not in st
           and now - datetime.fromisoformat(s["added_at"]) <= timedelta(hours=a.hours)][: a.max]
    print(f"stories: {len(stories)} live, {sum(1 for s in stories if s.get('breaking'))} breaking, {len(new)} to post")
    fails = 0
    for k, s in enumerate(new):
        name, tag, emo = CATS.get(s["category"], CATS["tech"])
        link = s["url"]
        text = (f"🔴 <b>فوری | {escape(s['title_fa'])}</b>\n\n{escape(cut(s['summary_fa'], 500))}\n\n"
                f"{emo} {tag} #نبض_فردا\n🔗 <a href=\"{escape(link)}\">منبع: {escape(s['source'])}</a> · <a href=\"{SITE}/#s={escape(s['id'])}\">استوری در نبض فردا</a>")
        print(f"- [{s['category']}] {s['id']} {s['title_fa'][:70]}")
        if a.dry_run:
            print("  " + text.replace("\n", "\n  ")); continue
        try:
            res = tg("sendMessage", {"chat_id": CFG["chat_id"], "text": text, "parse_mode": "HTML"})
        except RuntimeError as ex:
            print(f"  FAILED: {ex}"); fails += 1; continue
        st[s["id"]] = {"kind": "story", "at": now.isoformat(timespec="seconds"), "message_id": res["message_id"]}
        save_state(st)
        print(f"  OK message_id={res['message_id']}")
        if k < len(new) - 1:
            time.sleep(PAUSE)
    print(f"POSTED={0 if a.dry_run else len(new) - fails} FAILED={fails}" + (" (dry run)" if a.dry_run else ""))
    return 1 if fails else 0


def cmd_status(a):
    st = load_state()
    for k, v in sorted(st.items(), key=lambda x: x[1]["at"]):
        print(f"{v['at']}  {v['kind']:<7} {v.get('date', ''):<10} {k}  msg={v['message_id']}")
    print(f"{len(st)} posted")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("nightly")
    n.add_argument("date", nargs="?")
    n.add_argument("--max", type=int, default=8)
    n.add_argument("--limit", type=int)
    n.add_argument("--id", nargs="+")
    n.add_argument("--exclude", nargs="+", help="ids never to post (weak / soft stories)")
    n.add_argument("--no-verify", action="store_true")
    n.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("stories")
    s.add_argument("--max", type=int, default=3)
    s.add_argument("--hours", type=float, default=6)
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd != "status" and not getattr(a, "dry_run", False) and not TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN is not set")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit("another telegram_post.py run is in progress")
        sys.exit({"nightly": cmd_nightly, "stories": cmd_stories, "status": cmd_status}[a.cmd](a))


if __name__ == "__main__":
    main()
