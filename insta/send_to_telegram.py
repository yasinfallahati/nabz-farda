#!/usr/bin/env python3
"""Send a day's Instagram package (reel, carousel slides, caption) to the owner's Telegram DM.
Usage: send_to_telegram.py <dir> [--title TEXT]
Uses env TELEGRAM_BOT_TOKEN and owner_chat_id in /workspace/news-site/config/telegram.json."""
import os, sys, json, glob, time, requests
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API = f"https://api.telegram.org/bot{TOKEN}/"
CHAT = json.load(open("/workspace/news-site/config/telegram.json"))["owner_chat_id"]

def call(method, data=None, files=None):
    for attempt in range(4):
        try:
            r = requests.post(API + method, data=data, files=files, timeout=300)
            j = r.json()
            if j.get("ok"): return j
            ra = j.get("parameters", {}).get("retry_after")
            if ra: time.sleep(ra + 1); continue
            raise RuntimeError(f"{method} failed: {j.get('description')}")
        except requests.RequestException as e:
            time.sleep(3)
    raise RuntimeError(f"{method} failed after retries")

def main():
    d = sys.argv[1].rstrip("/")
    title = sys.argv[sys.argv.index("--title")+1] if "--title" in sys.argv else f"📦 پست امروز «نبض فردا» — {os.path.basename(d)}"
    call("sendMessage", {"chat_id": CHAT, "text": title})
    reel = os.path.join(d, "reel.mp4")
    if os.path.exists(reel):
        files = {"video": open(reel, "rb")}
        cover = os.path.join(d, "reel_cover.png")
        data = {"chat_id": CHAT, "caption": "🎬 ریلز", "supports_streaming": "true"}
        if os.path.exists(cover):
            files["cover"] = open(cover, "rb"); data["cover"] = "attach://cover"
        call("sendVideo", data, files)
    slides = sorted(glob.glob(os.path.join(d, "carousel", "*.png")) + glob.glob(os.path.join(d, "carousel", "*.jpg")))
    for i in range(0, len(slides), 10):
        chunk = slides[i:i+10]
        media, files = [], {}
        for k, p in enumerate(chunk):
            files[f"f{k}"] = open(p, "rb")
            media.append({"type": "photo", "media": f"attach://f{k}"})
        media[0]["caption"] = "🖼 اسلایدهای کروسل (به ترتیب)"
        call("sendMediaGroup", {"chat_id": CHAT, "media": json.dumps(media)}, files)
        # full-quality originals as documents
        media = [{"type": "document", "media": f"attach://f{k}"} for k in range(len(chunk))]
        files = {f"f{k}": open(p, "rb") for k, p in enumerate(chunk)}
        media[-1]["caption"] = "📎 همون اسلایدها با کیفیت اصلی"
        call("sendMediaGroup", {"chat_id": CHAT, "media": json.dumps(media)}, files)
    cap = os.path.join(d, "caption.txt")
    if os.path.exists(cap):
        call("sendMessage", {"chat_id": CHAT, "text": "📝 کپشن (نگه دار و کپی کن):"})
        call("sendMessage", {"chat_id": CHAT, "text": open(cap, encoding="utf-8").read()[:4096]})
    print("SENT", d)

if __name__ == "__main__":
    main()
