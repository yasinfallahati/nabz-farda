#!/usr/bin/env python3
"""
make_insta.py — build Instagram content (carousel + reel + caption) for «نبض فردا»
from one day JSON (public/data/days/YYYY-MM-DD.json).

Usage:
  python3 make_insta.py /workspace/news-site/public/data/days/2026-10-04.json
  python3 make_insta.py DAY.json --ids f143fce070,5b84f32013,...   # pick stories manually (in this order)
  python3 make_insta.py DAY.json --n 6 --out /tmp/x --no-reel
  python3 make_insta.py DAY.json --ids ... --style v1            # old static reel (v2 motion reel is the default)
  python3 make_insta.py DAY.json --ids ... --no-carousel          # reel + caption only
  python3 make_insta.py DAY.json --ids ID --single --hook 'سؤال *هوک*؟' --out DIR
        # one-story short reel (~14s, v2 look): hook question in the 1st second, story + summary, outro.
        # optional: --kick (chip above the hook), --sub (line under it), --sum (summary text), --tag (outro line),
        #           --beats (story length in beats, 0.5s each, default 16), --caption FILE (use this caption.txt)

Outputs (default /workspace/insta/<date>/):
  carousel/slide_01.png ... (1080x1350)   carousel_overview.png
  reel.mp4 (1080x1920, 30fps, H.264 + AAC, 25-35s; v2 = reel_v2.py)  reel_cover.png
  caption.txt                              stories.json (which stories were used)

Requirements: python3 + playwright (pip install playwright), Chromium/Chrome
(/usr/bin/google-chrome is used if present, else Playwright's own chromium), ffmpeg/ffprobe.
Fonts (Vazirmatn TTF) are loaded from ./assets/fonts next to this script — fully offline
apart from downloading the article images.
"""
import argparse, datetime as dt, hashlib, html, json, math, os, re, shutil, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "assets", "fonts")
CACHE = os.path.join(HERE, ".cache")
SITE_URL = "nabz-farda.vercel.app"
TODAY = {"kicker": "خبر داغ امروز", "title": "خلاصه اخبار امروز", "cap": "خلاصه اخبار امروز"}  # --past rewrites these
DEFAULT_CSS = "/workspace/news-site/public/assets/style.css"

CAT = {  # label, default colour (overridden from the site's style.css if found)
    "ai":   ["هوش مصنوعی", "#a78bfa"],
    "tech": ["تکنولوژی", "#22d3ee"],
    "game": ["گیم", "#fb7185"],
}
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
J_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]

def fa(s): return str(s).translate(FA_DIGITS)
def esc(s): return html.escape(str(s), quote=True)

def g2j(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053); days %= 12053
    jy += 4 * (days // 1461); days %= 1461
    if days > 365:
        jy += (days - 1) // 365; days = (days - 1) % 365
    if days < 186: jm, jd = 1 + days // 31, 1 + days % 31
    else: jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd

def jalali_label(iso):
    d = dt.date.fromisoformat(iso)
    jy, jm, jd = g2j(d.year, d.month, d.day)
    return f"{WEEKDAYS[d.weekday()]} {fa(jd)} {J_MONTHS[jm-1]} {fa(jy)}", (jy, jm, jd)

def load_site_colors(css_path):
    try:
        css = open(css_path, encoding="utf-8").read()
        for k in CAT:
            m = re.search(r"--%s:\s*(#[0-9a-fA-F]{3,8})" % k, css)
            if m: CAT[k][1] = m.group(1)
    except OSError:
        pass

# ---------------------------------------------------------------- story selection
FA_STOP = {"به", "در", "از", "با", "که", "و", "را", "برای", "تا", "این", "آن", "یک", "بر", "خود"}

def short_summary(s, limit=140):
    """Keep the summary to ~2 lines: first clause/sentence, cut at Persian punctuation."""
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= limit: return s
    for sep in ["؛", ". ", "! ", "؟ "]:
        head = s.split(sep)[0].strip()
        if 40 <= len(head) <= limit + 25:   # a complete clause may run a bit longer (font auto-shrinks)
            return head.rstrip(".،؛:") + "."
    cut = s[:limit]
    i = max(cut.rfind("،"), cut.rfind("؛"))
    if i < 60: i = cut.rfind(" ")
    words = cut[:i].rstrip(" .،؛:").split(" ")
    while len(words) > 3 and words[-1] in FA_STOP:   # never end on a dangling preposition
        words.pop()
    return " ".join(words).rstrip(" .،؛:") + "…"

HOWTO = re.compile(r"^(چطور|چگونه)|راهنمای|ترفند|تخفیف")
STOP = set("the a an of to in on for and with is are its it as by at from after how why what new".split())

def kw(title):
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 3 and w not in STOP}

def pick_stories(items, n, ids=None):
    if ids:
        by = {x["id"]: x for x in items}
        miss = [i for i in ids if i not in by]
        if miss: sys.exit(f"unknown ids: {miss}")
        return [by[i] for i in ids]
    pool = {k: [] for k in CAT}
    cand = sorted(items, key=lambda x: x.get("published", ""), reverse=True)
    cand = sorted(cand, key=lambda x: not x.get("featured"))   # featured first (stable)
    for x in cand:
        if x.get("category") in pool and x.get("image") and x.get("title_fa") and not HOWTO.search(x["title_fa"]):
            pool[x["category"]].append(x)
    order = ["ai", "tech", "game"]
    feat = next((x for x in cand if x.get("featured") and x in pool.get(x.get("category"), [])), None)
    if feat: order = [feat["category"]] + [c for c in order if c != feat["category"]]
    out, seen_kw = [], []
    while len(out) < n and any(pool.values()):
        for c in order:
            while pool[c]:
                x = pool[c].pop(0)
                k = kw(x.get("title", ""))
                if any(len(k & s) >= 2 for s in seen_kw):   # near-duplicate topic
                    continue
                out.append(x); seen_kw.append(k); break
            if len(out) >= n: break
    return out

# ---------------------------------------------------------------- images
def fetch_image(url):
    os.makedirs(os.path.join(CACHE, "img"), exist_ok=True)
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    for f in os.listdir(os.path.join(CACHE, "img")):
        if f.startswith(h): return os.path.join(CACHE, "img", f)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36",
        "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data, ct = r.read(), r.headers.get("Content-Type", "")
    except Exception as e:
        print(f"  ! image failed: {url} ({e})"); return None
    if len(data) < 2000 or not ct.startswith("image"):
        print(f"  ! not an image: {url} ({ct}, {len(data)}b)"); return None
    ext = {"image/png": ".png", "image/webp": ".webp", "image/avif": ".avif", "image/gif": ".gif"}.get(ct.split(";")[0], ".jpg")
    p = os.path.join(CACHE, "img", h + ext)
    open(p, "wb").write(data)
    return p

def file_url(p): return "file://" + urllib.request.pathname2url(os.path.abspath(p))

# ---------------------------------------------------------------- HTML
LOGO = ('<svg viewBox="0 0 48 48"><defs><linearGradient id="lg{n}" x1="0" x2="1"><stop offset="0" stop-color="#22d3ee"/>'
        '<stop offset=".5" stop-color="#a78bfa"/><stop offset="1" stop-color="#fb7185"/></linearGradient></defs>'
        '<path d="M3 26h9l4-10 7 20 6-26 5 16h11" fill="none" stroke="url(#lg{n})" stroke-width="4" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')
_logo_n = [0]
def logo():
    _logo_n[0] += 1
    return LOGO.replace("{n}", str(_logo_n[0]))

def brand(size=1.0):
    return (f'<div class="brand" style="--s:{size}"><span class="mark">{logo()}</span>'
            f'<span class="bt"><b>نبض فردا</b><small>هوش مصنوعی · تکنولوژی · گیم</small></span></div>')

def base_css(w, h):
    faces = "".join(
        f"@font-face{{font-family:Vazirmatn;src:url('{file_url(os.path.join(FONT_DIR, f'Vazirmatn-{n}.ttf'))}') format('truetype');font-weight:{wgt};font-display:block}}"
        for n, wgt in [("Regular", 400), ("Medium", 500), ("Bold", 700), ("ExtraBold", 800), ("Black", 900)])
    cols = ";".join(f"--{k}:{v[1]}" for k, v in CAT.items())
    return faces + f"""
:root{{--bg:#07080d;--bg2:#0d0f17;--txt:#e8eaf2;--mut:#9aa1b5;--dim:#6b7186;{cols}}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:transparent}}
body{{font-family:Vazirmatn,sans-serif;direction:rtl;color:var(--txt);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
.frame{{position:relative;width:{w}px;height:{h}px;overflow:hidden;background:var(--bg)}}
.frame.ov{{background:transparent}}
.brand{{display:flex;align-items:center;gap:calc(16px*var(--s))}}
.mark{{width:calc(68px*var(--s));height:calc(68px*var(--s));border-radius:calc(20px*var(--s));background:linear-gradient(145deg,#161a2a,#0c0e16);
  border:1px solid rgba(255,255,255,.1);display:grid;place-items:center;box-shadow:0 0 36px -6px rgba(167,139,250,.6)}}
.mark svg{{width:68%;height:68%}}
.bt{{display:flex;flex-direction:column;line-height:1.35}}
.bt b{{font-size:calc(38px*var(--s));font-weight:900;background:linear-gradient(90deg,#fff,#c4b5fd);-webkit-background-clip:text;background-clip:text;color:transparent}}
.bt small{{font-size:calc(19px*var(--s));color:var(--mut);font-weight:500}}
.pill{{display:inline-flex;align-items:center;gap:12px;font-size:27px;font-weight:800;padding:6px 22px 8px;border-radius:99px;color:var(--c);
  background:color-mix(in srgb,var(--c) 16%,rgba(7,8,13,.7));border:1.5px solid color-mix(in srgb,var(--c) 50%,transparent)}}
.pill .cnt{{font-style:normal;font-size:.85em;min-width:1.6em;height:1.6em;display:inline-grid;place-items:center;border-radius:99px;background:color-mix(in srgb,var(--c) 30%,transparent);color:#fff;margin-inline-start:4px;line-height:1}}
.pill i{{width:13px;height:13px;border-radius:50%;background:var(--c);box-shadow:0 0 14px var(--c)}}
.counter{{font-weight:800;font-size:26px;padding:6px 20px 8px;border-radius:99px;background:rgba(7,8,13,.6);border:1px solid rgba(255,255,255,.14);color:#fff}}
.accent{{position:absolute;bottom:0;left:0;right:0;height:8px;background:linear-gradient(90deg,#22d3ee,#a78bfa,#fb7185)}}
.grad-txt{{background:linear-gradient(90deg,#fff 10%,#c4b5fd 55%,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent}}
.url{{direction:ltr;unicode-bidi:isolate;display:inline-block;font-weight:800;letter-spacing:.5px}}
.ico{{width:1em;height:1em;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;vertical-align:-.15em}}
"""

FIT_JS = """
async () => {
  await document.fonts.ready;
  await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => {i.onload=i.onerror=r})));
  const warn = [];
  for (const el of document.querySelectorAll('[data-lines]')) {
    const max = +el.dataset.lines, min = +(el.dataset.min || 20);
    let fs = parseFloat(getComputedStyle(el).fontSize);
    const lines = () => Math.round(el.scrollHeight / parseFloat(getComputedStyle(el).lineHeight));
    while (lines() > max && fs > min) { fs -= 1; el.style.fontSize = fs + 'px'; }
    if (lines() > max) { el.style.display='-webkit-box'; el.style.webkitLineClamp=max; el.style.webkitBoxOrient='vertical'; el.style.overflow='hidden';
                         warn.push('clamped: ' + el.textContent.slice(0,40)); }
  }
  const missing = [...document.images].filter(i => !i.naturalWidth).map(i => i.src);
  if (missing.length) warn.push('image not loaded: ' + missing.join(', '));
  return warn;
}"""

def icons():
    heart = '<svg class="ico" viewBox="0 0 24 24"><path d="M12 21s-7.5-4.6-9.5-9.3C1.2 8.6 3.3 5 6.8 5c2 0 3.4 1.1 4.2 2.4C11.8 6.1 13.2 5 15.2 5c3.5 0 5.6 3.6 4.3 6.7C19.5 16.4 12 21 12 21z"/></svg>'
    save = '<svg class="ico" viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4-6 4z"/></svg>'
    share = '<svg class="ico" viewBox="0 0 24 24"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/></svg>'
    follow = '<svg class="ico" viewBox="0 0 24 24"><circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-6.5 7-6.5s7 2.5 7 6.5M19 8v6M16 11h6"/></svg>'
    return heart, save, share, follow

def page(w, h, body, extra_css="", ov=False):
    return (f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{base_css(w, h)}{extra_css}</style></head>'
            f'<body><div class="frame{" ov" if ov else ""}">{body}</div></body></html>')

# ---- carousel (1080x1350)
CAR_CSS = """
.top{position:absolute;top:50px;left:60px;right:60px;display:flex;justify-content:space-between;align-items:center;z-index:3}
.s-img{position:absolute;top:0;left:0;right:0;height:840px;background:#0d0f17 center/cover no-repeat}
.s-shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,.75) 0,rgba(7,8,13,0) 17%,rgba(7,8,13,0) 36%,rgba(7,8,13,.82) 54%,#07080d 63%)}
.s-glow{position:absolute;inset:0;background:radial-gradient(760px 460px at 100% 100%,color-mix(in srgb,var(--c) 20%,transparent),transparent 70%),
  radial-gradient(600px 360px at 0% 70%,rgba(167,139,250,.08),transparent 70%)}
.s-body{position:absolute;left:66px;right:66px;bottom:92px;z-index:2}
.s-body h1{font-size:60px;line-height:1.52;font-weight:900;margin:24px 0 14px;text-wrap:balance;text-shadow:0 2px 20px rgba(0,0,0,.5)}
.s-body p{font-size:34px;line-height:1.72;color:#c9cdda;font-weight:500;text-wrap:pretty}
.s-src{margin-top:28px;display:flex;align-items:center;gap:18px;font-size:26px;color:var(--mut);font-weight:600}
.s-src b{color:#fff;font-weight:800}
.s-src .ln{flex:1;height:1px;background:rgba(255,255,255,.12)}
.s-src .url{color:var(--dim);font-weight:600;font-size:24px}
/* cover */
.mosaic{position:absolute;inset:-160px -200px auto -200px;height:1000px;display:grid;grid-template-columns:repeat(4,1fr);gap:22px;transform:rotate(-8deg);opacity:.55}
.mosaic div{border-radius:26px;background:#11131d center/cover;aspect-ratio:4/3}
.c-shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,.7) 0,rgba(7,8,13,.35) 20%,rgba(7,8,13,.85) 48%,#07080d 62%),
  radial-gradient(900px 500px at 85% 100%,rgba(167,139,250,.22),transparent 60%),radial-gradient(700px 420px at 0% 85%,rgba(34,211,238,.14),transparent 60%)}
.c-body{position:absolute;left:66px;right:66px;bottom:100px;z-index:2}
.kicker{font-size:30px;font-weight:700;color:var(--mut);display:flex;align-items:center;gap:14px}
.kicker .dot{width:14px;height:14px;border-radius:50%;background:#34d399;box-shadow:0 0 0 6px rgba(52,211,153,.2)}
.c-title{font-size:118px;line-height:1.35;font-weight:900;margin:18px 0 10px;letter-spacing:-1px}
.c-date{font-size:44px;font-weight:800;color:#fff}
.chips{display:flex;gap:14px;margin-top:34px;flex-wrap:wrap}
.swipe{margin-top:40px;font-size:28px;color:var(--mut);font-weight:600;display:flex;align-items:center;gap:12px}
.swipe svg{width:40px;height:40px;fill:none;stroke:#c4b5fd;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
/* cta */
.cta-bg{position:absolute;inset:0;background:radial-gradient(900px 600px at 80% 0%,rgba(167,139,250,.25),transparent 60%),
  radial-gradient(800px 520px at 0% 40%,rgba(34,211,238,.14),transparent 60%),radial-gradient(900px 600px at 50% 110%,rgba(251,113,133,.16),transparent 60%)}
.pulse{position:absolute;left:-40px;right:-40px;top:430px;height:300px;opacity:.12}
.cta{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:0 80px;gap:0}
.cta .bigmark{width:180px;height:180px;border-radius:50px;background:linear-gradient(145deg,#161a2a,#0c0e16);border:1px solid rgba(255,255,255,.12);display:grid;place-items:center;box-shadow:0 0 90px -10px rgba(167,139,250,.7)}
.cta .bigmark svg{width:70%;height:70%}
.cta h2{font-size:84px;font-weight:900;margin-top:40px;line-height:1.4}
.cta .lead{font-size:38px;color:#c9cdda;font-weight:600;margin-top:34px}
.cta .urlbox{margin-top:20px;font-size:46px;padding:18px 44px 22px;border-radius:26px;background:rgba(255,255,255,.05);border:1.5px solid rgba(167,139,250,.5);box-shadow:0 0 0 8px rgba(167,139,250,.08)}
.cta .follow{margin-top:52px;font-size:36px;font-weight:800;padding:20px 48px 24px;border-radius:99px;background:linear-gradient(135deg,#a78bfa,#22d3ee);color:#07080d;display:inline-flex;gap:14px;align-items:center}
.cta .acts{margin-top:40px;display:flex;gap:44px;font-size:30px;color:var(--mut);font-weight:600}
.cta .acts span{display:inline-flex;gap:10px;align-items:center}
.cta .sub{font-size:30px;color:var(--mut);margin-top:22px;font-weight:500;line-height:1.7}
"""

def counter(i, n): return f'<span class="counter"><bdi dir="ltr">{fa(i)}/{fa(n)}</bdi></span>'

def pill(cat, extra=""):
    lab, col = CAT.get(cat, ["خبر", "#a78bfa"])
    return f'<span class="pill" style="--c:{col}"><i></i>{lab}{extra}</span>'

def chips(stories):
    cnt = {}
    for s in stories: cnt[s["category"]] = cnt.get(s["category"], 0) + 1
    return "".join(pill(c, f'<em class="cnt">{fa(cnt[c])}</em>') for c in CAT if c in cnt)

def car_cover(stories, date_label, n):
    tiles = [s["_img"] for s in stories if s.get("_img")]
    tiles = (tiles * 3)[:12] if tiles else []
    mos = "".join(f'<div style="background-image:url(\'{file_url(t)}\')"></div>' for t in tiles)
    return page(1080, 1350, f"""
<div class="mosaic">{mos}</div><div class="c-shade"></div>
<div class="top">{brand(1.0)}{counter(1, n)}</div>
<div class="c-body">
  <div class="kicker"><span class="dot"></span>{fa(len(stories))} {TODAY["kicker"]}</div>
  <h1 class="c-title grad-txt">{TODAY["title"]}</h1>
  <div class="c-date">{esc(date_label)}</div>
  <div class="chips">{chips(stories)}</div>
  <div class="swipe">برای دیدن خبرها ورق بزنید<svg viewBox="0 0 24 24"><path d="M19 12H5M11 6l-6 6 6 6"/></svg></div>
</div><div class="accent"></div>""", CAR_CSS)

def car_story(s, i, n):
    col = CAT.get(s["category"], ["", "#a78bfa"])[1]
    img = f"background-image:url('{file_url(s['_img'])}')" if s.get("_img") else \
          f"background:radial-gradient(600px 400px at 70% 40%,{col}55,transparent),#0d0f17"
    return page(1080, 1350, f"""
<div class="s-img" style="{img}"></div><div class="s-shade"></div><div class="s-glow" style="--c:{col}"></div>
<div class="top">{brand(0.85)}{counter(i, n)}</div>
<div class="s-body" style="--c:{col}">
  {pill(s['category'])}
  <h1 data-lines="3" data-min="48">{esc(s['title_fa'])}</h1>
  <p data-lines="2" data-min="28">{esc(s['_sum'])}</p>
  <div class="s-src">منبع: <b><bdi>{esc(s['source'])}</bdi></b><span class="ln"></span><span class="url">{SITE_URL}</span></div>
</div><div class="accent"></div>""", CAR_CSS)

PULSE = ('<svg class="pulse" viewBox="0 0 1160 300" preserveAspectRatio="none"><path d="M0 160h300l60-120 90 240 80-260 70 190 60-50h500" '
         'fill="none" stroke="#a78bfa" stroke-width="6" stroke-linejoin="round"/></svg>')

def car_cta(n):
    heart, save, share, follow = icons()
    return page(1080, 1350, f"""
<div class="cta-bg"></div>{PULSE}
<div class="top">{brand(0.85)}{counter(n, n)}</div>
<div class="cta">
  <div class="bigmark">{logo()}</div>
  <h2 class="grad-txt">نبض فردا</h2>
  <div class="sub">هر شب، خلاصهٔ داغ‌ترین خبرهای هوش مصنوعی، تکنولوژی و گیم</div>
  <div class="lead">برای خبرهای بیشتر:</div>
  <div class="urlbox"><span class="url">{SITE_URL}</span></div>
  <div class="follow">{follow} ما را دنبال کنید</div>
  <div class="acts"><span>{heart} لایک</span><span>{save} ذخیره</span><span>{share} ارسال برای دوستان</span></div>
</div><div class="accent"></div>""", CAR_CSS)

# ---- reel (1080x1920): background layer (zoomed by ffmpeg) + transparent text overlay
# Safe zone used: top 230px, bottom 440px, right 150px (Reels UI buttons), left 70px.
REEL_CSS = """
.r-blur{position:absolute;inset:-80px;background:center/cover no-repeat;filter:blur(46px) brightness(.42) saturate(1.3)}
.r-card{position:absolute;top:350px;left:60px;right:60px;height:600px;border-radius:40px;background:#11131d center/cover no-repeat;
  box-shadow:0 30px 80px -10px rgba(0,0,0,.8),0 0 0 1.5px rgba(255,255,255,.12)}
.r-tint{position:absolute;inset:0;background:radial-gradient(800px 600px at 100% 100%,color-mix(in srgb,var(--c) 28%,transparent),transparent 70%)}
.r-shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,.75) 0,rgba(7,8,13,0) 12%,rgba(7,8,13,0) 47%,rgba(7,8,13,.88) 55%,rgba(7,8,13,.94) 100%)}
.r-top{position:absolute;top:236px;left:70px;right:150px;display:flex;justify-content:space-between;align-items:center}
.r-top .counter{font-size:28px}
.r-body{position:absolute;left:70px;right:150px;bottom:450px}
.r-row{display:flex;align-items:center;gap:18px;font-size:27px;color:var(--mut);font-weight:700}
.r-row b{color:#fff}
.r-body h1{font-size:56px;line-height:1.5;font-weight:900;margin:22px 0 14px;text-wrap:balance;text-shadow:0 2px 24px rgba(0,0,0,.6)}
.r-body p{font-size:33px;line-height:1.7;color:#cfd3df;font-weight:500;text-wrap:pretty}
.rc-mosaic{position:absolute;inset:-300px -320px;display:grid;grid-template-columns:repeat(3,1fr);gap:26px;transform:rotate(-10deg);opacity:.6;align-content:center}
.rc-mosaic div{border-radius:30px;background:#11131d center/cover;aspect-ratio:4/3}
.rc-shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,.85) 0,rgba(7,8,13,.55) 25%,rgba(7,8,13,.9) 45%,rgba(7,8,13,.95) 100%),
  radial-gradient(900px 600px at 90% 75%,rgba(167,139,250,.25),transparent 60%),radial-gradient(800px 500px at 0% 55%,rgba(34,211,238,.16),transparent 60%)}
.rc{position:absolute;left:70px;right:150px;top:880px}
.rc .c-title{font-size:116px;line-height:1.35;font-weight:900;margin:22px 0 18px;letter-spacing:-1px}
.rc .kicker{font-size:32px;font-weight:700;color:var(--mut);display:flex;align-items:center;gap:14px}
.rc .kicker .dot{width:15px;height:15px;border-radius:50%;background:#34d399;box-shadow:0 0 0 6px rgba(52,211,153,.2)}
.rc .c-date{font-size:46px;font-weight:800}
.rc .chips{display:flex;gap:14px;margin-top:40px;flex-wrap:wrap}
.cta-bg{position:absolute;inset:0;background:radial-gradient(1000px 800px at 80% 10%,rgba(167,139,250,.28),transparent 60%),
  radial-gradient(900px 700px at 0% 50%,rgba(34,211,238,.16),transparent 60%),radial-gradient(1000px 700px at 50% 100%,rgba(251,113,133,.18),transparent 60%),#07080d}
.pulse{position:absolute;left:-60px;right:-60px;top:720px;height:420px;opacity:.13}
.rcta{position:absolute;top:230px;bottom:440px;left:70px;right:150px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.rcta .bigmark{width:200px;height:200px;border-radius:56px;background:linear-gradient(145deg,#161a2a,#0c0e16);border:1px solid rgba(255,255,255,.12);display:grid;place-items:center;box-shadow:0 0 100px -10px rgba(167,139,250,.75)}
.rcta .bigmark svg{width:70%;height:70%}
.rcta h2{font-size:92px;font-weight:900;margin-top:44px;line-height:1.4}
.rcta .sub{font-size:31px;color:var(--mut);margin-top:16px;font-weight:500;line-height:1.7}
.rcta .lead{font-size:40px;color:#d4d7e2;font-weight:600;margin-top:56px}
.rcta .urlbox{margin-top:22px;font-size:44px;padding:18px 40px 22px;border-radius:26px;background:rgba(255,255,255,.05);border:1.5px solid rgba(167,139,250,.5);box-shadow:0 0 0 8px rgba(167,139,250,.08)}
.rcta .follow{margin-top:56px;font-size:38px;font-weight:800;padding:20px 50px 24px;border-radius:99px;background:linear-gradient(135deg,#a78bfa,#22d3ee);color:#07080d;display:inline-flex;gap:14px;align-items:center}
.rcta .acts{margin-top:40px;display:flex;gap:40px;font-size:30px;color:var(--mut);font-weight:600}
.rcta .acts span{display:inline-flex;gap:10px;align-items:center}
"""

def reel_story_bg(s):
    col = CAT.get(s["category"], ["", "#a78bfa"])[1]
    u = f"background-image:url('{file_url(s['_img'])}')" if s.get("_img") else f"background:radial-gradient(500px 400px at 60% 40%,{col}66,#0d0f17)"
    return page(1080, 1920, f'<div class="r-blur" style="{u}"></div><div class="r-tint" style="--c:{col}"></div><div class="r-card" style="{u}"></div>', REEL_CSS)

def reel_story_ov(s, i, n):
    col = CAT.get(s["category"], ["", "#a78bfa"])[1]
    return page(1080, 1920, f"""<div class="r-shade"></div>
<div class="r-top">{brand(0.9)}{counter(i, n)}</div>
<div class="r-body" style="--c:{col}">
  <div class="r-row">{pill(s['category'])}<span>منبع: <b><bdi>{esc(s['source'])}</bdi></b></span></div>
  <h1 data-lines="3" data-min="44">{esc(s['title_fa'])}</h1>
  <p data-lines="3" data-min="28">{esc(s['_sum'])}</p>
</div>""", REEL_CSS, ov=True)

def reel_cover_bg(stories):
    tiles = [s["_img"] for s in stories if s.get("_img")]
    tiles = (tiles * 4)[:18] if tiles else []
    mos = "".join(f'<div style="background-image:url(\'{file_url(t)}\')"></div>' for t in tiles)
    return page(1080, 1920, f'<div class="rc-mosaic">{mos}</div><div class="rc-shade"></div>', REEL_CSS)

def reel_cover_ov(stories, date_label):
    return page(1080, 1920, f"""
<div class="r-top">{brand(1.0)}</div>
<div class="rc">
  <div class="kicker"><span class="dot"></span>{fa(len(stories))} {TODAY["kicker"]}</div>
  <h1 class="c-title grad-txt">{TODAY["title"]}</h1>
  <div class="c-date">{esc(date_label)}</div>
  <div class="chips">{chips(stories)}</div>
</div>""", REEL_CSS, ov=True)

def reel_cta_bg():
    return page(1080, 1920, f'<div class="cta-bg"></div>{PULSE}', REEL_CSS)

def reel_cta_ov():
    heart, save, share, follow = icons()
    return page(1080, 1920, f"""
<div class="rcta">
  <div class="bigmark">{logo()}</div>
  <h2 class="grad-txt">نبض فردا</h2>
  <div class="sub">هر شب، خلاصهٔ داغ‌ترین خبرهای<br>هوش مصنوعی، تکنولوژی و گیم</div>
  <div class="lead">برای خبرهای بیشتر:</div>
  <div class="urlbox"><span class="url">{SITE_URL}</span></div>
  <div class="follow">{follow} ما را دنبال کنید</div>
  <div class="acts"><span>{heart} لایک</span><span>{save} ذخیره</span><span>{share} ارسال</span></div>
</div>""", REEL_CSS, ov=True)

# ---------------------------------------------------------------- rendering
class Renderer:
    def __init__(self, build):
        from playwright.sync_api import sync_playwright
        self.build = build
        self.pw = sync_playwright().start()
        exe = next((p for p in ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"] if os.path.exists(p)), None)
        self.browser = self.pw.chromium.launch(executable_path=exe, args=["--no-sandbox", "--allow-file-access-from-files", "--font-render-hinting=none"])
        self.warnings = []

    def shot(self, html_str, out_png, w, h, scale=1, transparent=False):
        name = os.path.splitext(os.path.basename(out_png))[0]
        hp = os.path.join(self.build, name + ".html")
        open(hp, "w", encoding="utf-8").write(html_str)
        pg = self.browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
        pg.goto(file_url(hp), wait_until="load")
        warn = pg.evaluate(FIT_JS)
        pg.wait_for_timeout(120)
        pg.screenshot(path=out_png, omit_background=transparent, clip={"x": 0, "y": 0, "width": w, "height": h})
        pg.close()
        for wmsg in warn:
            self.warnings.append(f"{os.path.basename(out_png)}: {wmsg}"); print("  ! " + self.warnings[-1])

    def close(self):
        self.browser.close(); self.pw.stop()

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:]); raise SystemExit(f"command failed: {' '.join(cmd[:6])}...")
    return r

def make_segment(bg, ov, out, dur, mode, fps=30):
    """Ken Burns on the (2x resolution) background + text overlay that fades/slides in."""
    N = int(round(dur * fps))
    p = f"(on/{N - 1})"
    ease = f"(0.5-0.5*cos(PI*{p}))"
    z = f"1+0.10*{ease}" if mode == "in" else f"1.10-0.10*{ease}"
    # keep the focal point (card centre ~ x540,y650 in 1080 space -> 2x) fixed while zooming
    fx, fy = 1080, 1300
    vf = (f"[0:v]zoompan=z='{z}':x='{fx}*(1-1/zoom)':y='{fy}*(1-1/zoom)':d=1:s=1080x1920:fps={fps},setsar=1[b];"
          f"[1:v]format=rgba,fade=in:st=0.15:d=0.7:alpha=1[o];"
          f"[b][o]overlay=x=0:y='if(lt(t,0.15),46,if(lt(t,0.85),46*pow(1-(t-0.15)/0.7,2),0))':eval=frame:shortest=1,"
          f"format=yuv420p[v]")
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-t", f"{dur}", "-i", bg,
         "-loop", "1", "-framerate", str(fps), "-t", f"{dur}", "-i", ov,
         "-filter_complex", vf, "-map", "[v]", "-frames:v", str(N), "-r", str(fps),
         "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", out])

def music_expr(total):
    """Generated ambient beat (no samples -> no copyright): soft pad chord progression,
    sub kick on every beat (100 BPM), off-beat hats, gentle arpeggio pluck."""
    b = 0.6  # seconds per beat
    m = f"mod(t,{b})"
    bar = f"mod(floor(t/{4*b}),4)"  # 4-bar loop Am - F - C - G
    root = f"if(eq({bar},0),220,if(eq({bar},1),174.61,if(eq({bar},2),261.63,196)))"
    third = f"if(eq({bar},0),261.63,if(eq({bar},1),220,if(eq({bar},2),329.63,246.94)))"
    fifth = f"if(eq({bar},0),329.63,if(eq({bar},1),261.63,if(eq({bar},2),392,293.66)))"
    pad = (f"0.055*(sin(2*PI*{root}*t)+0.8*sin(2*PI*{third}*t)+0.7*sin(2*PI*{fifth}*t)+0.5*sin(2*PI*{root}/2*t)+0.15*sin(2*PI*{root}*2.003*t))"
           f"*(0.75+0.25*sin(2*PI*0.2*t))*min(1,mod(t,{4*b})*5)*min(1,({4*b}-mod(t,{4*b}))*5)")  # soft chord changes
    kick = f"0.42*sin(2*PI*(48*{m}+3.2*(1-exp(-28*{m}))))*exp(-7*{m})"
    hat = f"0.035*(2*random(0)-1)*exp(-70*mod(t+{b/2},{b}))"
    q = f"mod(t,{b/2})"
    step = f"mod(floor(t/{b/2}),4)"
    arp_f = f"if(eq({step},0),{root}*2,if(eq({step},1),{third}*2,if(eq({step},2),{fifth}*2,{third}*2)))"
    arp = f"0.05*sin(2*PI*{arp_f}*t)*exp(-6*{q})*gte(t,{8*b})"
    return f"({pad}+{kick}+{hat}+{arp})"

def make_reel(r, stories, date_label, build, out_mp4, cover_png):
    n = len(stories)
    scenes = [("cover", None, 3.4, "in")]
    for k, s in enumerate(stories):
        scenes.append(("story", s, 3.6, "in" if k % 2 == 0 else "out"))
    scenes.append(("cta", None, 4.0, "in"))
    segs = []
    for k, (kind, s, dur, mode) in enumerate(scenes):
        bg = os.path.join(build, f"reel_bg_{k:02d}.png"); ov = os.path.join(build, f"reel_ov_{k:02d}.png")
        if kind == "cover":
            r.shot(reel_cover_bg(stories), bg, 1080, 1920, scale=2)
            r.shot(reel_cover_ov(stories, date_label), ov, 1080, 1920, transparent=True)
        elif kind == "cta":
            r.shot(reel_cta_bg(), bg, 1080, 1920, scale=2)
            r.shot(reel_cta_ov(), ov, 1080, 1920, transparent=True)
        else:
            r.shot(reel_story_bg(s), bg, 1080, 1920, scale=2)
            r.shot(reel_story_ov(s, k, n), ov, 1080, 1920, transparent=True)
        seg = os.path.join(build, f"seg_{k:02d}.mp4")
        print(f"  segment {k+1}/{len(scenes)} ({kind}, {dur}s)")
        make_segment(bg, ov, seg, dur, mode)
        segs.append((seg, dur))
    # reel cover image (for the Reels thumbnail): first frame-ish composite of the cover scene
    run(["ffmpeg", "-y", "-v", "error", "-ss", "1.2", "-i", segs[0][0], "-frames:v", "1", cover_png])
    T = 0.5
    total = sum(d for _, d in segs) - T * (len(segs) - 1)
    inputs, fc, prev, off = [], [], "[0:v]", 0.0
    for seg, _ in segs: inputs += ["-i", seg]
    for k in range(1, len(segs)):
        off += segs[k - 1][1] - T
        lab = f"[x{k}]" if k < len(segs) - 1 else "[vx]"
        fc.append(f"{prev}[{k}:v]xfade=transition=fade:duration={T}:offset={off:.3f}{lab}")
        prev = lab
    fc.append(f"[vx]fade=out:st={total-0.6:.3f}:d=0.6,format=yuv420p[v]")
    expr = music_expr(total)
    fc.append(f"aevalsrc='{expr}|{expr}':s=44100:d={total:.3f},lowpass=f=9000,"
              f"aecho=0.8:0.6:180|360:0.25|0.12,afade=t=in:d=1.2,afade=t=out:st={total-2.2:.3f}:d=2.2,"
              f"loudnorm=I=-16:TP=-1.5:LRA=11,aformat=channel_layouts=stereo[a]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", "30",
         "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", "-t", f"{total:.3f}", out_mp4])
    return total

# ---------------------------------------------------------------- caption
TAGS = [("openai", "#OpenAI"), ("nvidia", "#Nvidia #انویدیا"), ("steam", "#Steam #استیم"), ("witcher", "#Witcher #ویچر"),
        ("meta", "#Meta #متا"), ("متا", "#Meta #متا"), ("tsmc", "#TSMC"), ("musk", "#ElonMusk #ایلان_ماسک"), ("capcom", "#Capcom #کپکام"),
        ("apple", "#Apple #اپل"), ("google", "#Google #گوگل"), ("xbox", "#Xbox #ایکس_باکس"), ("playstation", "#PlayStation #پلی_استیشن"),
        ("ps5", "#PS5"), ("netflix", "#Netflix #نتفلیکس"), ("agent", "#AIAgents #ایجنت_هوش_مصنوعی"), ("valorant", "#Valorant"),
        ("gpt", "#ChatGPT"), ("chip", "#Semiconductors #تراشه"), ("privacy", "#Privacy #حریم_خصوصی"), ("muse", "#Privacy #حریم_خصوصی")]
EMO = {"ai": "🤖", "tech": "💻", "game": "🎮"}

def caption(stories, date_label, with_summary=True):
    nums = "1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣ 8️⃣ 9️⃣".split()
    lines = [f"⚡️ {TODAY['cap']} | {date_label}", "",
             f"{fa(len(stories))} خبر داغ از دنیای هوش مصنوعی، تکنولوژی و گیم در یک نگاه 👇", ""]
    for k, s in enumerate(stories):
        lines.append(f"{nums[k] if k < len(nums) else '▫️'} {EMO.get(s['category'], '📰')} {s['title_fa']}")
        if with_summary:
            lines.append(f"   {s['_sum']} (منبع: {s['source']})")
            lines.append("")
    if not with_summary: lines.append("")
    lines += ["📌 کدام خبر برایت جالب‌تر بود؟ در کامنت‌ها بنویس.",
              "🔖 این پست را ذخیره کن و برای دوستانت بفرست.", "",
              f"🌐 برای خبرهای بیشتر: {SITE_URL}",
              "🔔 «نبض فردا» را دنبال کن تا هر شب خلاصهٔ خبرها را از دست ندهی.", ""]
    tags = ["#نبض_فردا", "#خلاصه_اخبار", "#اخبار_روز", "#اخبار_تکنولوژی", "#هوش_مصنوعی", "#تکنولوژی", "#گیم", "#بازی", "#فناوری"]
    blob = " ".join((s.get("title", "") + " " + s.get("title_fa", "")).lower() for s in stories)
    for key, t in TAGS:
        if key in blob:
            for tt in t.split():
                if tt not in tags: tags.append(tt)
    tags += ["#AI", "#ArtificialIntelligence", "#Tech", "#TechNews", "#Gaming", "#GamingNews", "#Technology"]
    seen, out = set(), []
    for t in tags:
        if t not in seen: seen.add(t); out.append(t)
    lines.append(" ".join(out[:30]))   # Instagram allows max 30 hashtags
    text = "\n".join(lines) + "\n"
    if len(text) > 2200:   # Instagram caption limit: drop per-story summaries, then everything optional
        return caption(stories, date_label, False) if with_summary else caption_short(stories, date_label, lines[-1])
    return text

def caption_short(stories, date_label, tagline):
    lines = [f"⚡️ {TODAY['cap']} | {date_label}", ""]
    lines += [f"{EMO.get(s['category'], '📰')} {s['title_fa']}" for s in stories]
    lines += ["", f"🌐 برای خبرهای بیشتر: {SITE_URL}", "🔔 «نبض فردا» را دنبال کن.", "", tagline]
    return "\n".join(lines) + "\n"

def caption_single(s, hook=None):
    """caption for a one-story reel: hook, summary, CTA, bio link, ~15 hashtags."""
    hook = (hook or s["title_fa"]).replace("*", "")
    lines = [f"{EMO.get(s['category'], '📰')} {hook}", "", s["title_fa"], s.get("summary_fa", ""), f"(منبع: {s['source']})", "",
             "💬 نظرت چیه؟ در کامنت‌ها بنویس.", "🔖 ذخیره کن و برای یه رفیق بفرست.",
             "🔔 برای خبرهای داغ هر روز @nabz_farda رو دنبال کن.", "🔗 لینک خبر کامل در بیو", ""]
    tags = ["#نبض_فردا", "#اخبار_تکنولوژی", {"ai": "#هوش_مصنوعی", "tech": "#تکنولوژی", "game": "#گیم"}.get(s["category"], "#تکنولوژی")]
    blob = (s.get("title", "") + " " + s.get("title_fa", "")).lower()
    for key, t in TAGS:
        if key in blob: tags += [x for x in t.split() if x not in tags]
    tags += {"ai": ["#AI", "#ArtificialIntelligence", "#TechNews"], "tech": ["#Tech", "#TechNews", "#Technology"],
             "game": ["#Gaming", "#GamingNews", "#بازی"]}.get(s["category"], ["#TechNews"])
    lines.append(" ".join(dict.fromkeys(tags)))
    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------- contact sheet
def contact_sheet(r, slides, out_png, title):
    cols = 3; tw, th = 360, 450; gap = 24; pad = 40
    rows = math.ceil(len(slides) / cols)
    W = pad * 2 + cols * tw + (cols - 1) * gap
    H = pad * 2 + 90 + rows * th + (rows - 1) * gap
    cells = "".join(f'<img src="{file_url(p)}">' for p in slides)
    css = f""".sheet{{padding:{pad}px}} .sheet h3{{font-size:34px;font-weight:900;height:90px;display:flex;align-items:center;gap:14px}}
.grid{{direction:ltr;display:grid;grid-template-columns:repeat({cols},{tw}px);gap:{gap}px}} .grid img{{width:{tw}px;height:{th}px;border-radius:14px;box-shadow:0 0 0 1px rgba(255,255,255,.1)}}"""
    r.shot(page(W, H, f'<div class="sheet"><h3>{brand(0.6)}<span style="color:var(--mut);font-weight:600;font-size:28px">{esc(title)}</span></h3><div class="grid">{cells}</div></div>', css),
           out_png, W, H)

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("day_json", nargs="+", help="day JSON(s); several files are merged (date/label from the first)")
    ap.add_argument("--out", help="output dir (default: <script dir>/<date>)")
    ap.add_argument("--ids", help="comma-separated story ids, in display order (default: automatic pick)")
    ap.add_argument("--n", type=int, default=7, help="number of stories when picking automatically (5-7)")
    ap.add_argument("--css", default=DEFAULT_CSS, help="site style.css to read accent colours from")
    ap.add_argument("--no-reel", action="store_true")
    ap.add_argument("--no-carousel", action="store_true", help="skip the carousel slides (reel + caption only)")
    ap.add_argument("--style", choices=["v2", "v1"], default="v2",
                    help="reel style: v2 = motion-graphics reel (default), v1 = old static Ken-Burns reel")
    ap.add_argument("--past", action="store_true", help="wording for a past day (no «امروز»), e.g. catch-up posts")
    g = ap.add_argument_group("single-story short reel (--single)")
    g.add_argument("--single", action="store_true", help="one story -> short standalone reel (implies --no-carousel)")
    g.add_argument("--hook", help="hook text shown from frame 0, e.g. a question; wrap words in *..* to highlight")
    g.add_argument("--kick", help="small chip above the hook (default: category label)")
    g.add_argument("--sub", default="", help="line under the hook (e.g. «ماجرا چیه؟»)")
    g.add_argument("--sum", action="append", help="summary text shown under the title (default: short summary_fa); "
                   "repeat once per story, in --ids order")
    g.add_argument("--with-sum", action="store_true", help="multi-story v2 reel: show a summary line under each title "
                   "(card moves up; use with --beats ~14 and --hook/--kick/--sub for the opening)")
    g.add_argument("--tag", help="outro line (default: «لینک خبر کامل در بیو» + tagline)")
    g.add_argument("--beats", type=int, help="story scene length in beats (120 BPM; default 16 = 8s single, auto for multi)")
    g.add_argument("--bpm", type=int, help="multi v2 reel: tempo (default 120); scene lengths are in beats of this tempo")
    g.add_argument("--hook-beats", type=int, help="multi v2 reel: hook length in beats (default 4, or 6 with --sub/--with-sum)")
    g.add_argument("--outro-beats", type=int, help="multi v2 reel: outro length in beats (default 6)")
    g.add_argument("--speed", type=float, help="multi v2 reel: entrance-animation speed factor (e.g. 1.4 for short/tight reels)")
    g.add_argument("--kb", type=float, help="multi v2 reel: Ken Burns amplitude factor (e.g. 1.6 = more motion)")
    g.add_argument("--cut", type=float, help="multi v2 reel: transition length in seconds (default 0.4)")
    g.add_argument("--caption", help="use this caption file instead of the generated one")
    a = ap.parse_args()
    if a.single:
        a.no_carousel = True; a.style = "v2"
        if not a.ids or len(a.ids.split(",")) != 1: sys.exit("--single needs exactly one --ids")
    if a.past: TODAY.update(kicker="خبر داغ روز", title="خلاصه اخبار روز", cap="خلاصه اخبار")

    load_site_colors(a.css)
    day = json.load(open(a.day_json[0], encoding="utf-8"))
    for extra in a.day_json[1:]:
        seen = {x["id"] for x in day["items"]}
        day["items"] += [x for x in json.load(open(extra, encoding="utf-8"))["items"] if x["id"] not in seen]
    date = day["date"]
    out = a.out or os.path.join(HERE, date)
    build = os.path.join(CACHE, "build", date + ("-single-" + hashlib.sha1(os.path.abspath(out).encode()).hexdigest()[:8] if (a.single or a.with_sum or a.hook) else ""))
    shutil.rmtree(build, ignore_errors=True); os.makedirs(build)
    os.makedirs(out, exist_ok=True)
    if not a.single:
        os.makedirs(os.path.join(out, "carousel"), exist_ok=True)
        for f in os.listdir(os.path.join(out, "carousel")):
            if f.endswith(".png"): os.remove(os.path.join(out, "carousel", f))

    date_label, _ = jalali_label(date)
    ids = [x.strip() for x in a.ids.split(",")] if a.ids else None
    stories = pick_stories(day["items"], max(1, a.n), ids)
    print(f"{date} ({date_label}): {len(stories)} stories")
    for s in stories:
        s["_img"] = fetch_image(s["image"]) if s.get("image") else None
    for k, s in enumerate(stories):
        s["_sum"] = a.sum[k] if (a.sum and k < len(a.sum)) else short_summary(s.get("summary_fa", ""), 110 if (a.single or a.with_sum) else 140)
        print(f"  [{s['category']}] {s['id']} {s['source']}: {s['title_fa']}")

    r = Renderer(build)
    try:
      if not a.no_carousel:
        n = len(stories) + 2
        slides = []
        def sp(i): p = os.path.join(out, "carousel", f"slide_{i:02d}.png"); slides.append(p); return p
        r.shot(car_cover(stories, date_label, n), sp(1), 1080, 1350)
        for k, s in enumerate(stories, start=2):
            r.shot(car_story(s, k, n), sp(k), 1080, 1350)
        r.shot(car_cta(n), sp(n), 1080, 1350)
        contact_sheet(r, slides, os.path.join(out, "carousel_overview.png"), f"کاروسل اینستاگرام · {date_label}")
        print(f"carousel: {len(slides)} slides")
      if not a.no_reel:
            if a.style == "v2":
                sys.path.insert(0, HERE)
                from reel_v2 import make_reel_v2
                texts = {"kick": TODAY["title"], "hook": TODAY["kicker"],
                         "tag": "هر شب، خلاصهٔ داغ‌ترین خبرهای\nهوش مصنوعی، تکنولوژی و گیم"}
                single = multi = None
                if not a.single and (a.with_sum or a.beats or a.hook or a.bpm or a.speed):
                    multi = {"withsum": a.with_sum, "hook_beats": a.hook_beats or (6 if (a.sub or a.with_sum) else 4)}
                    for k_, v_ in [("bpm", a.bpm), ("outro_beats", a.outro_beats), ("spd", a.speed), ("kb", a.kb), ("tw", a.cut)]:
                        if v_: multi[k_] = v_
                    if a.beats: multi["beats"] = a.beats
                    if a.hook: texts["hook"] = a.hook
                    if a.kick: texts["kick"] = a.kick
                    if a.sub: texts["date"] = a.sub
                    if a.tag: texts["tag"] = a.tag
                if a.single:
                    texts["tag"] = a.tag or "لینک خبر کامل در بیو\nهر روز داغ‌ترین خبرهای هوش مصنوعی، تکنولوژی و گیم"
                    single = {"hook": a.hook or stories[0]["title_fa"], "kick": a.kick, "sub": a.sub, "beats": a.beats or 16}
                total = make_reel_v2(stories, date_label, build, os.path.join(out, "reel.mp4"), os.path.join(out, "reel_cover.png"),
                                     CAT, texts, SITE_URL, single=single, multi=multi)
                if a.single or multi: shutil.copyfile(os.path.join(out, "reel_cover.png"), os.path.join(out, "cover.png"))
            else:
                total = make_reel(r, stories, date_label, build, os.path.join(out, "reel.mp4"), os.path.join(out, "reel_cover.png"))
            print(f"reel ({a.style}): {total:.1f}s")
    finally:
        r.close()

    if a.caption: cap = open(a.caption, encoding="utf-8").read()
    elif a.single: cap = caption_single(stories[0], a.hook)
    else: cap = caption(stories, date_label)
    open(os.path.join(out, "caption.txt"), "w", encoding="utf-8").write(cap)
    json.dump({"date": date, "date_jalali": date_label, "stories": [{k: v for k, v in s.items() if not k.startswith("_")} | {"summary_short": s["_sum"]} for s in stories],
               "warnings": r.warnings}, open(os.path.join(out, "stories.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done ->", out, "| warnings:", len(r.warnings))

if __name__ == "__main__":
    main()
