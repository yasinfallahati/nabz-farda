#!/usr/bin/env python3
"""Static page generator for نبض فردا (called by build.py; can also run alone: sitegen.py).

From every public/data/days/*.json it (re)generates:
  public/news/<DATE>/<ID>.html     one page per story (served as /news/<DATE>/<ID> thanks to cleanUrls)
  public/news/<DATE>/index.html    static day page (all stories of that day)
  public/news/index.html           archive of all days
  public/og/<DATE>/<ID>.png        1200x630 Open Graph image per story (cached; only redrawn when its text changes)
  public/og/default.png            site-wide OG image; public/assets/logo-512.png, apple-touch-icon.png
  public/sitemap.xml, sitemap-news.xml (Google News, last 48h), robots.txt, feed.xml (RSS 2.0)
HTML output is deterministic (no build timestamps), so unchanged pages keep the same hash and are not re-uploaded.
"""
import hashlib, html, json, os, re, sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
SITE = os.environ.get("SITE_URL", "https://nabz-farda.vercel.app").rstrip("/")
NAME = "نبض فردا"
TAGLINE = "اخبار روز هوش مصنوعی، تکنولوژی و گیم"
DESC = "نبض فردا — خلاصهٔ فارسی مهم‌ترین اخبار روز دنیای هوش مصنوعی، تکنولوژی و بازی‌های ویدیویی از معتبرترین رسانه‌های جهان. هر شب ساعت ۰۰:۰۰ به‌روز می‌شود."
FONTS = Path(os.environ.get("NF_FONTS", "/workspace/insta/assets/fonts"))
OG_MANIFEST = ROOT / "data/og-manifest.json"
OG_VERSION = "v4"
TEH = ZoneInfo("Asia/Tehran")
CATS = {"ai": ("هوش مصنوعی", "#a78bfa"), "tech": ("تکنولوژی", "#22d3ee"), "game": ("گیم", "#fb7185")}
ORDER = ["ai", "tech", "game"]
ANALYTICS = ('<script>window.va=window.va||function(){(window.vaq=window.vaq||[]).push(arguments)};</script>'
             '<script defer src="/_vercel/insights/script.js"></script>')
E = lambda s: html.escape(str(s or ""), quote=True)

# ---------------------------------------------------------------- Persian dates
FA_DIG = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def fa(x):
    return str(x).translate(FA_DIG)


def g2j(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053); days %= 12053
    jy += 4 * (days // 1461); days %= 1461
    if days > 365:
        jy += (days - 1) // 365; days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return jy, jm, jd


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def jdate(dt, weekday=False, year=True):
    t = dt.astimezone(TEH) if dt.tzinfo else dt
    jy, jm, jd = g2j(t.year, t.month, t.day)
    s = f"{fa(jd)} {MONTHS[jm - 1]}" + (f" {fa(jy)}" if year else "")
    return (WDAYS[t.weekday()] + " " + s) if weekday else s


def day_label(date):  # "YYYY-MM-DD" Tehran calendar date
    return jdate(datetime.fromisoformat(date + "T12:00:00"), weekday=True)


def tehran_time(dt):
    return fa(dt.astimezone(TEH).strftime("%H:%M"))


# ---------------------------------------------------------------- data
def load_days():
    days = []
    for f in sorted((PUB / "data/days").glob("*.json"), reverse=True):
        d = json.loads(f.read_text())
        for it in d["items"]:
            it["_date"] = d["date"]
        days.append(d)
    return days


def page_path(date, id_):
    return f"/news/{date}/{id_}"


def toks(s):
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower())} - {
        "the", "and", "for", "with", "from", "that", "this", "its", "new", "you", "your", "are", "has", "have", "will", "how", "why", "what", "after", "into", "about", "now", "out"}


def related(it, pool, n=3):
    """Prefer same category and same/adjacent calendar day; fall back to token overlap."""
    a, t0 = toks(it["title"]), parse_ts(it["published"])
    day0 = it.get("_date") or t0.astimezone(TEH).strftime("%Y-%m-%d")
    scored = []
    for o in pool:
        if o is it or o["id"] == it["id"]:
            continue
        b = toks(o["title"])
        j = len(a & b) / (len(a | b) or 1)
        dd = abs((parse_ts(o["published"]) - t0).total_seconds()) / 86400
        day1 = o.get("_date") or parse_ts(o["published"]).astimezone(TEH).strftime("%Y-%m-%d")
        try:
            day_delta = abs((datetime.fromisoformat(day0) - datetime.fromisoformat(day1)).days)
        except Exception:
            day_delta = 99
        same_cat = 2.5 if o["category"] == it["category"] else 0
        adj = 2.0 if day_delta == 0 else (1.2 if day_delta == 1 else 0)
        s = 3 * j + same_cat + adj + 1 / (1 + dd)
        scored.append((s, o["published"], o))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [o for _, _, o in scored[:n]]


def reading_mins(it):
    """Estimate reading time from body_fa (preferred) or summary_fa. Persian ~180 wpm."""
    text = (it.get("body_fa") or it.get("summary_fa") or "").strip()
    words = len(text.split()) or max(1, len(text) // 5)
    return max(1, round(words / 180))


# ---------------------------------------------------------------- OG images
def _font(w, size):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONTS / f"Vazirmatn-{w}.ttf"), size, layout_engine=ImageFont.Layout.RAQM)


def _rtl_w(f, s):
    return f.getlength(s, direction="rtl", language="fa")


def _wrap(text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if _rtl_w(f, t) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


ACC, BG, TXT, MUT, DIM, LINE = "#ff5a4e", "#0b0c0f", "#ececee", "#a1a2a9", "#6f7078", "#1f2026"


def _logo(d, x, y, s, k=None, color=ACC):
    """Pulse mark (same path as favicon/header) in a 48-unit box at (x,y), scale s, single accent colour."""
    pts = [(3, 26), (12, 26), (16, 16), (23, 36), (29, 10), (34, 26), (45, 26)]
    P = [(x + px * s, y + py * s) for px, py in pts]
    w = max(2, int(4 * s))
    d.line(P, fill=color, width=w, joint="curve")
    for p in (P[0], P[-1]):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=color)


def _canvas(K):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1200 * K, 630 * K), BG)
    return im, ImageDraw.Draw(im)


def _brand(d, K, right, y=88):
    """Accent pulse mark + brand name, anchored to the right edge (RTL), vertically centred on y."""
    s = 1.05 * K
    _logo(d, right - 48 * s, y * K - 24 * s, s)
    d.text((right - 48 * s - 14 * K, y * K), NAME, font=_font("Bold", 34 * K), fill=TXT, anchor="rm", direction="rtl", language="fa")


def og_article(it, out):
    K = 2
    im, d = _canvas(K)
    W, H, M = 1200 * K, 630 * K, 80 * K
    cat_fa = CATS.get(it["category"], CATS["tech"])[0]
    _brand(d, K, W - M)
    d.text((M, 88 * K), cat_fa, font=_font("Medium", 28 * K), fill=ACC, anchor="lm", direction="rtl", language="fa")
    title = (it.get("title_fa") or it["title"]).strip()
    maxw, top, bottom = W - 2 * M, 165 * K, 500 * K
    for size in (74, 68, 62, 56, 52, 48, 44):
        f = _font("Bold", size * K)
        lines = _wrap(title, f, maxw)
        lh = int(size * 1.6 * K)
        if len(lines) * lh <= bottom - top:
            break
    maxl = (bottom - top) // lh
    if len(lines) > maxl:
        lines = lines[:maxl]
        while _rtl_w(f, lines[-1] + " …") > maxw and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += " …"
    y = top + ((bottom - top) - len(lines) * lh) // 2
    for ln in lines:
        d.text((W - M, y + lh // 2), ln, font=f, fill="#ffffff", anchor="rm", direction="rtl", language="fa")
        y += lh
    d.line([M, 532 * K, W - M, 532 * K], fill=LINE, width=2 * K)
    mf = _font("Regular", 27 * K)
    ds = jdate(parse_ts(it["published"]), weekday=True)   # separate runs -> no bidi mixing of Latin source + Persian date
    d.text((W - M, 574 * K), ds, font=mf, fill=MUT, anchor="rm", direction="rtl", language="fa")
    x = W - M - _rtl_w(mf, ds) - 20 * K
    d.line([x, 562 * K, x, 586 * K], fill="#3a3b42", width=2 * K)
    d.text((x - 20 * K, 574 * K), it["source"], font=_font("Medium", 27 * K), fill=TXT, anchor="rm")
    d.text((M, 574 * K), SITE.split("//")[1], font=_font("Regular", 24 * K), fill=DIM, anchor="lm")
    _save(im, out)


def og_default(out):
    K = 2
    im, d = _canvas(K)
    W, H = 1200 * K, 630 * K
    s = 2.6 * K
    _logo(d, (W - 48 * s) / 2, 175 * K - 24 * s, s)
    d.text((W // 2, 315 * K), NAME, font=_font("Bold", 96 * K), fill="#ffffff", anchor="mm", direction="rtl", language="fa")
    d.text((W // 2, 420 * K), TAGLINE + " — به فارسی", font=_font("Regular", 34 * K), fill=MUT, anchor="mm", direction="rtl", language="fa")
    cf = _font("Medium", 27 * K)
    names = [CATS[c][0] for c in ORDER]
    gap = 44 * K
    ws = [_rtl_w(cf, t) for t in names]
    x = (W + sum(ws) + gap * (len(ws) - 1)) / 2
    for k, (t, w) in enumerate(zip(names, ws)):
        d.text((x, 520 * K), t, font=cf, fill=TXT if k == 0 else TXT, anchor="rm", direction="rtl", language="fa")
        x -= w
        if k < len(ws) - 1:
            d.line([x - gap / 2, 506 * K, x - gap / 2, 534 * K], fill="#3a3b42", width=2 * K)
        x -= gap
    _save(im, out)


def logo_png(out, size):
    from PIL import Image, ImageDraw
    K = 4
    im = Image.new("RGBA", (size * K, size * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size * K - 1, size * K - 1], radius=size * K // 4, fill=BG)
    s = size * K / 48 * 0.78
    _logo(d, (size * K - 48 * s) / 2, (size * K - 48 * s) / 2 + 1.5 * s, s)
    im = im.resize((size, size), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)


def _save(im, out):
    from PIL import Image
    im = im.resize((1200, 630), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)


def og_images(items):
    man = json.loads(OG_MANIFEST.read_text()) if OG_MANIFEST.exists() else {}
    made = 0
    for it in items:
        key = f"{it['_date']}/{it['id']}"
        h = hashlib.sha1(json.dumps([OG_VERSION, it.get("title_fa") or it["title"], it["category"], it["source"],
                                     it["published"], SITE], ensure_ascii=False).encode()).hexdigest()[:16]
        out = PUB / f"og/{key}.png"
        if man.get(key) != h or not out.exists():
            og_article(it, out); man[key] = h; made += 1
    for p, fn in ((PUB / "og/default.png", og_default),):
        if man.get("_default") != OG_VERSION + SITE or not p.exists():
            fn(p); man["_default"] = OG_VERSION + SITE; made += 1
    if man.get("_logo") != OG_VERSION or not (PUB / "assets/logo-512.png").exists():
        logo_png(PUB / "assets/logo-512.png", 512); logo_png(PUB / "assets/apple-touch-icon.png", 180)
        man["_logo"] = OG_VERSION; made += 1
    OG_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OG_MANIFEST.write_text(json.dumps(man, indent=0, sort_keys=True))
    return made


# ---------------------------------------------------------------- HTML
ASSET_V = "4"
SITE_NAV = [
    ("home", "/", "خانه"),
    ("archive", "/news/", "بایگانی"),
    ("automation", "/automation/", "اتوماسیون"),
    ("about", "/about/", "درباره"),
    ("api", "/api/", "API"),
]


def head(title, desc, canonical, og_image, og_type="website", extra="", active=None):
    nav = "".join(
        f'<a href="{h}"{" class=\"active\"" if k == active else ""}>{t}</a>'
        for k, h, t in SITE_NAV
    )
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
<meta name="theme-color" content="#0b0c0f">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:site_name" content="{NAME}">
<meta property="og:locale" content="fa_IR">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:image" content="{E(og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{E(title)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}">
<meta name="twitter:image" content="{E(og_image)}">
{extra}<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="alternate" type="application/rss+xml" title="{NAME}" href="{SITE}/feed.xml">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css">
<link rel="stylesheet" href="/assets/style.css?v={ASSET_V}">
<link rel="stylesheet" href="/assets/article.css?v={ASSET_V}">
{ANALYTICS}
</head>
<body class="page">
<header class="hdr"><div class="wrap hdr-in">
  <a class="logo" href="/" aria-label="{NAME}"><svg class="logo-mark" viewBox="0 0 48 48" aria-hidden="true"><path d="M3 26h9l4-10 7 20 6-26 5 16h11"/></svg><span>{NAME}</span></a>
  <nav class="nav site-nav" aria-label="منوی اصلی">{nav}</nav>
  <div class="hdr-tools">
    <a class="auto-badge" href="/automation/" title="سیستم اتوماتیک">سیستم اتوماتیک</a>
    <a class="icon-btn" href="/search/" aria-label="جست‌وجو"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4-4"/></svg></a>
  </div>
</div></header>
"""


FOOT = f"""<footer class="ftr">
  <div class="wrap ftr-in">
    <div class="ftr-about"><b>{NAME}</b><p>خلاصهٔ فارسی مهم‌ترین اخبار هوش مصنوعی، تکنولوژی و گیم از معتبرترین رسانه‌های جهان. حقوق محتوای اصلی متعلق به منابع آن است.</p></div>
    <nav class="ftr-links" aria-label="پیوندها">
      <a href="/">خانه</a>
      <a href="/news/">بایگانی</a>
      <a href="/automation/">اتوماسیون</a>
      <a href="/about/">درباره</a>
      <a href="/api/">API</a>
      <a href="/feed.xml">فید RSS</a>
    </nav>
  </div>
</footer>
<script src="/assets/site.js?v={ASSET_V}" defer></script>
</body>
</html>
"""


def ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n"


ORG = {"@type": "NewsMediaOrganization", "@id": SITE + "/#org", "name": NAME, "url": SITE + "/",
       "logo": {"@type": "ImageObject", "url": SITE + "/assets/logo-512.png", "width": 512, "height": 512}}


def media(o, eager=False, alt=""):
    fb = f'<div class="fallback"><span>{E(o["source"])}</span></div>'
    if not o.get("image"):
        return fb
    return fb + (f'<img class="img" src="{E(o["image"])}" alt="{E(alt)}" loading="{"eager" if eager else "lazy"}" decoding="async" '
                 f'referrerpolicy="no-referrer" onerror="this.classList.add(\'broken\')">')


def mini_card(o):
    """Same card as the homepage list (image, category as quiet text, title, source · date)."""
    cat_fa = CATS.get(o["category"], CATS["tech"])[0]
    dt = parse_ts(o["published"])
    return (f'<a class="card" data-cat="{E(o["category"])}" href="{page_path(o["_date"], o["id"])}">'
            f'<div class="media">{media(o)}</div><div class="txt"><span class="kicker">{cat_fa}</span>'
            f'<h3>{E(o.get("title_fa") or o["title"])}</h3>'
            f'<div class="meta"><span class="src">{E(o["source"])}</span><i class="sep"></i>'
            f'<time datetime="{E(o["published"])}">{jdate(dt, year=False)}</time></div></div></a>')


def article_html(it, rel, is_latest):
    url = SITE + page_path(it["_date"], it["id"])
    og = f"{SITE}/og/{it['_date']}/{it['id']}.png"
    title = it.get("title_fa") or it["title"]
    summ = it.get("summary_fa") or ""
    cat_fa, _ = CATS.get(it["category"], CATS["tech"])
    dt = parse_ts(it["published"])
    desc = summ if len(summ) <= 300 else summ[:297].rsplit(" ", 1)[0] + "…"
    back = "/" if is_latest else f"/?d={it['_date']}"
    extra = (f'<meta property="article:published_time" content="{E(it["published"])}">\n'
             f'<meta property="article:section" content="{cat_fa}">\n')
    jl = [{"@context": "https://schema.org", "@type": "NewsArticle", "@id": url + "#article",
           "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "headline": title[:110], "alternativeHeadline": it["title"],
           "description": desc, "image": [og], "datePublished": it["published"], "dateModified": it["published"],
           "inLanguage": "fa-IR", "articleSection": cat_fa, "isBasedOn": it["link"],
           "author": {"@type": "Organization", "name": NAME, "url": SITE + "/"},
           "publisher": ORG, "sourceOrganization": {"@type": "Organization", "name": it["source"]}},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": NAME, "item": SITE + "/"},
              {"@type": "ListItem", "position": 2, "name": day_label(it["_date"]), "item": f"{SITE}/news/{it['_date']}/"},
              {"@type": "ListItem", "position": 3, "name": title[:110], "item": url}]}]
    img = f'<figure class="art-media media">{media(it, True, title)}</figure>' if it.get("image") else ""
    share_t = f"https://t.me/share/url?url={E(url)}&amp;text={E(title)}"
    share_x = f"https://twitter.com/intent/tweet?url={E(url)}&amp;text={E(title)}"
    rel_html = "".join(mini_card(o) for o in rel)
    host = re.sub(r"^https?://(www\.)?", "", it["link"]).split("/")[0]
    body_raw = (it.get("body_fa") or "").strip()
    body_ps = "".join(f"<p>{E(para.strip())}</p>" for para in body_raw.split("\n\n") if para.strip()) if body_raw else ""
    summary_sec = f'<section class="art-sec art-sec-summary"><h2 class="art-sec-h">خلاصه</h2><p class="art-summary">{E(summ)}</p></section>'
    body_sec = (f'<section class="art-sec art-sec-body"><h2 class="art-sec-h">خبر کامل</h2><div class="art-body">{body_ps}</div></section>'
                if body_ps else "")
    note = (f'پوشش فارسی خبری از {E(it["source"])}؛ منبع: <a href="{E(it["link"])}" target="_blank" rel="noopener" dir="ltr">{E(host)}</a>'
            if body_raw else
            f'خلاصهٔ فارسی خبری از {E(it["source"])}؛ منبع: <a href="{E(it["link"])}" target="_blank" rel="noopener" dir="ltr">{E(host)}</a>')
    mins = reading_mins(it)
    read_fa = fa(mins)
    return (head(f"{title} | {NAME}", desc, url, og, "article", extra + ld(jl[0]) + ld(jl[1]), active="archive") +
            f"""<main class="wrap art-wrap">
<nav class="crumbs" aria-label="مسیر"><a href="/">{NAME}</a><span aria-hidden="true">/</span><a href="/news/{it['_date']}/">{day_label(it['_date'])}</a></nav>
<article class="article" data-cat="{E(it['category'])}">
  <header class="art-head">
    <a class="kicker" href="/?c={E(it['category'])}">{cat_fa}</a>
    <h1>{E(title)}</h1>
    <p class="art-en" dir="ltr" lang="en">{E(it['title'])}</p>
    <div class="meta art-meta"><span class="src">{E(it['source'])}</span><i class="sep"></i><time datetime="{E(it['published'])}">{jdate(dt, weekday=True)}، ساعت {tehran_time(dt)}</time><i class="sep"></i><span class="read-time">{read_fa} دقیقه مطالعه</span></div>
  </header>
  {img}
  {summary_sec}
  {body_sec}
  <div class="art-actions">
    <a class="btn" href="{E(it['link'])}" target="_blank" rel="noopener">خواندن در {E(it['source'])}<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 5h5v5M19 5l-8 8M17 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h4"/></svg></a>
    <div class="share"><span>اشتراک:</span>
      <button type="button" class="share-copy" data-url="{E(url)}" aria-label="کپی لینک">کپی لینک</button>
      <a href="{share_t}" target="_blank" rel="noopener">تلگرام</a>
      <a href="{share_x}" target="_blank" rel="noopener">X</a>
    </div>
  </div>
  <p class="art-note">{note}</p>
</article>
{f'<section class="related"><h2>خبرهای مرتبط</h2><div class="list cols-3">{rel_html}</div></section>' if rel else ''}
<a class="back-link" href="{back}">بازگشت به اخبار {'امروز' if is_latest else day_label(it['_date'])}</a>
</main>
""" + FOOT)


def day_html(d, is_latest):
    date = d["date"]
    url = f"{SITE}/news/{date}/"
    lab = day_label(date)
    title = f"اخبار {lab} | {NAME}"
    desc = f"گزیدهٔ {fa(len(d['items']))} خبر مهم هوش مصنوعی، تکنولوژی و گیم در {lab} با تیتر و خلاصهٔ فارسی."
    secs = []
    for c in ORDER:
        its = [i for i in d["items"] if i["category"] == c]
        if its:
            secs.append(f'<section class="day-sec"><div class="latest-head"><h2>{CATS[c][0]}</h2><span class="count">{fa(len(its))} خبر</span></div>'
                        f'<div class="list">' + "".join(mini_card(i) for i in its) + "</div></section>")
    jl = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "url": url, "inLanguage": "fa-IR",
          "isPartOf": {"@id": SITE + "/#website"},
          "mainEntity": {"@type": "ItemList", "itemListElement": [
              {"@type": "ListItem", "position": k + 1, "url": SITE + page_path(date, i["id"])} for k, i in enumerate(d["items"])]}}
    return (head(title, desc, url, SITE + "/og/default.png", extra=ld(jl)) +
            f"""<main class="wrap page-wrap">
<nav class="crumbs"><a href="/">{NAME}</a><span aria-hidden="true">/</span><a href="/news/">آرشیو</a></nav>
<div class="page-head"><h1>{lab}</h1><p>{fa(len(d['items']))} خبر، <a href="{'/' if is_latest else '/?d=' + date}">نمایش در صفحهٔ اصلی</a></p></div>
{''.join(secs)}
</main>
""" + FOOT)


def index_html(days):
    url = SITE + "/news/"
    rows = "".join(f'<a class="day-row" href="/news/{d["date"]}/"><span>{day_label(d["date"])}{"<em>امروز</em>" if k == 0 else ""}</span><small>{fa(len(d["items"]))} خبر</small></a>'
                   for k, d in enumerate(days))
    return (head(f"آرشیو اخبار | {NAME}", "آرشیو روزانهٔ اخبار هوش مصنوعی، تکنولوژی و گیم نبض فردا به فارسی.", url, SITE + "/og/default.png") +
            f"""<main class="wrap page-wrap narrow">
<nav class="crumbs"><a href="/">{NAME}</a></nav>
<div class="page-head"><h1>آرشیو روزها</h1><p>{fa(len(days))} روز، {fa(sum(len(d['items']) for d in days))} خبر</p></div>
<div class="day-list">{rows}</div>
</main>
""" + FOOT)


# ---------------------------------------------------------------- feeds
def xml(s):
    return html.escape(str(s or ""), quote=False)


def write(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists() or p.read_text() != s:
        p.write_text(s)


def sitemaps(days, items):
    latest_up = days[0]["updated_at"]
    urls = [(SITE + "/", latest_up, "hourly", "1.0"),
            (SITE + "/news/", latest_up, "daily", "0.6"),
            (SITE + "/automation/", latest_up, "daily", "0.5"),
            (SITE + "/about/", latest_up, "monthly", "0.5"),
            (SITE + "/api/", latest_up, "monthly", "0.4"),
            (SITE + "/search/", latest_up, "weekly", "0.4")]
    for d in days:
        urls.append((f"{SITE}/news/{d['date']}/", d["updated_at"], "daily", "0.5"))
    for it in items:
        urls.append((SITE + page_path(it["_date"], it["id"]), it["published"], "monthly", "0.8"))
    body = "".join(f"<url><loc>{xml(u)}</loc><lastmod>{m}</lastmod><changefreq>{c}</changefreq><priority>{p}</priority></url>\n" for u, m, c, p in urls)
    write(PUB / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n")
    # Google News sitemap: articles from the 48h before the newest article
    newest = max(parse_ts(i["published"]) for i in items)
    recent = [i for i in items if parse_ts(i["published"]) >= newest - timedelta(hours=48)][:1000]
    nb = "".join(f"<url><loc>{xml(SITE + page_path(i['_date'], i['id']))}</loc><news:news><news:publication><news:name>{NAME}</news:name>"
                 f"<news:language>fa</news:language></news:publication><news:publication_date>{i['published']}</news:publication_date>"
                 f"<news:title>{xml(i.get('title_fa') or i['title'])}</news:title></news:news></url>\n" for i in recent)
    write(PUB / "sitemap-news.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n' + nb + "</urlset>\n")
    write(PUB / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\nSitemap: {SITE}/sitemap-news.xml\n")
    return len(urls)


def rss(items, n=60):
    its = sorted(items, key=lambda i: i["published"], reverse=True)[:n]
    last = format_datetime(parse_ts(its[0]["published"]).astimezone(timezone.utc), usegmt=True)
    out = []
    for i in its:
        u = SITE + page_path(i["_date"], i["id"])
        og = f"{SITE}/og/{i['_date']}/{i['id']}.png"
        p = PUB / f"og/{i['_date']}/{i['id']}.png"
        size = p.stat().st_size if p.exists() else 0
        out.append(f"""<item><title>{xml(i.get('title_fa') or i['title'])}</title><link>{xml(u)}</link><guid isPermaLink="true">{xml(u)}</guid>
<pubDate>{format_datetime(parse_ts(i['published']).astimezone(timezone.utc), usegmt=True)}</pubDate><category>{CATS.get(i['category'], CATS['tech'])[0]}</category>
<source url="{xml(i['link'])}">{xml(i['source'])}</source><description>{xml(i.get('summary_fa'))}</description>
<enclosure url="{og}" length="{size}" type="image/png"/><media:content url="{og}" medium="image" width="1200" height="630" type="image/png"/></item>""")
    write(PUB / "feed.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
<channel><title>{NAME} — {TAGLINE}</title><link>{SITE}/</link><description>{xml(DESC)}</description><language>fa</language>
<lastBuildDate>{last}</lastBuildDate><atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>
<image><url>{SITE}/assets/logo-512.png</url><title>{NAME}</title><link>{SITE}/</link></image>
{chr(10).join(out)}
</channel></rss>
""")
    return len(its)


# ---------------------------------------------------------------- competition artifacts (ops / search / API)


def short_commit():
    try:
        import subprocess
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return ""


def write_search_index(items):
    rows = []
    for it in items:
        rows.append({
            "id": it["id"],
            "date": it["_date"],
            "title_fa": it.get("title_fa") or it["title"],
            "summary_fa": it.get("summary_fa") or "",
            "category": it["category"],
            "url": page_path(it["_date"], it["id"]),
            "source": it["source"],
        })
    write(PUB / "data/search-index.json", json.dumps({"generated_at": datetime.now(TEH).isoformat(timespec="seconds"),
                                                       "count": len(rows), "items": rows}, ensure_ascii=False, separators=(",", ":")))
    return len(rows)


def write_ops(days, items):
    latest = days[0] if days else None
    by_cat = {"ai": 0, "tech": 0, "game": 0}
    if latest:
        for it in latest["items"]:
            by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1
    stories, stories_updated = [], None
    sp = PUB / "data/stories.json"
    if sp.exists():
        try:
            stories = json.loads(sp.read_text())
            stories_updated = datetime.fromtimestamp(sp.stat().st_mtime, tz=TEH).isoformat(timespec="seconds")
        except Exception:
            stories = []
    tg_day = 0
    tg_path = ROOT / "data/telegram/posted.json"
    if tg_path.exists() and latest:
        try:
            posted = json.loads(tg_path.read_text())
            tg_day = sum(1 for v in posted.values() if isinstance(v, dict) and v.get("date") == latest["date"])
        except Exception:
            tg_day = 0
    feeds = 0
    fp = ROOT / "scripts/feeds.json"
    if fp.exists():
        try:
            feeds = len(json.loads(fp.read_text()))
        except Exception:
            feeds = 0
    now_teh = datetime.now(TEH)
    ops = {
        "version": 1,
        "site": SITE,
        "name": NAME,
        "build_at": now_teh.isoformat(timespec="seconds"),
        "build_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": "Asia/Tehran",
        "commit": short_commit(),
        "last_nightly_date": latest["date"] if latest else None,
        "latest_item_count": len(latest["items"]) if latest else 0,
        "item_counts_by_category": by_cat,
        "archive_days": len(days),
        "total_articles": len(items),
        "stories_live": len(stories) if isinstance(stories, list) else 0,
        "stories_updated_at": stories_updated,
        "telegram_posted_today": tg_day,
        "feed_count": feeds,
        "pipeline": [
            {"id": "fetch", "label_fa": "جمع‌آوری", "label_en": "Fetch"},
            {"id": "translate", "label_fa": "ترجمه", "label_en": "Translate"},
            {"id": "build", "label_fa": "ساخت و سئو", "label_en": "Build/SEO"},
            {"id": "deploy", "label_fa": "انتشار", "label_en": "Deploy"},
            {"id": "telegram", "label_fa": "تلگرام", "label_en": "Telegram"},
            {"id": "instagram", "label_fa": "اینستاگرام", "label_en": "Instagram"},
        ],
    }
    text = json.dumps(ops, ensure_ascii=False, indent=2)
    write(PUB / "data/ops.json", text)
    return ops


def write_api(days, items, ops):
    api = PUB / "api/v1"
    api.mkdir(parents=True, exist_ok=True)
    latest = days[0] if days else {"date": None, "items": []}
    latest_items = []
    for it in latest.get("items", []):
        latest_items.append({
            "id": it["id"],
            "category": it["category"],
            "source": it["source"],
            "title_fa": it.get("title_fa") or it["title"],
            "summary_fa": it.get("summary_fa") or "",
            "published": it["published"],
            "url": page_path(it["_date"], it["id"]),
            "link": it.get("link"),
        })
    write(api / "latest.json", json.dumps({
        "date": latest.get("date"),
        "count": len(latest_items),
        "items": latest_items,
        "generated_at": ops.get("build_at"),
    }, ensure_ascii=False, separators=(",", ":")))
    arch = {"latest": days[0]["date"] if days else None,
            "days": [{"date": d["date"], "count": len(d["items"]), "updated_at": d.get("updated_at")} for d in days]}
    write(api / "archive.json", json.dumps(arch, ensure_ascii=False, separators=(",", ":")))
    write(api / "ops.json", json.dumps(ops, ensure_ascii=False, indent=2))
    openapi = {
        "openapi": "3.0.3",
        "info": {
            "title": "Nabz-e Farda Public API",
            "description": "Static JSON endpoints for the Nabz-e Farda Persian news site. No auth required.",
            "version": "1.0.0",
        },
        "servers": [{"url": SITE + "/api/v1"}],
        "paths": {
            "/latest.json": {
                "get": {
                    "summary": "Latest day items",
                    "responses": {"200": {"description": "Today's (or newest) articles summary"}},
                }
            },
            "/archive.json": {
                "get": {
                    "summary": "Archive day index",
                    "responses": {"200": {"description": "Thin list of available days"}},
                }
            },
            "/ops.json": {
                "get": {
                    "summary": "Pipeline / ops snapshot",
                    "responses": {"200": {"description": "Build timestamp, counts, stories, telegram"}},
                }
            },
        },
    }
    write(api / "openapi.json", json.dumps(openapi, ensure_ascii=False, indent=2))



def generate():
    days = load_days()
    if not days:
        return "no days"
    items = [i for d in days for i in d["items"]]
    made = og_images(items)
    keep = set()
    for k, d in enumerate(days):
        for it in d["items"]:
            p = PUB / f"news/{d['date']}/{it['id']}.html"
            write(p, article_html(it, related(it, items), k == 0)); keep.add(p)
        p = PUB / f"news/{d['date']}/index.html"
        write(p, day_html(d, k == 0)); keep.add(p)
    write(PUB / "news/index.html", index_html(days)); keep.add(PUB / "news/index.html")
    stale = [p for p in (PUB / "news").rglob("*.html") if p not in keep]   # e.g. a story later marked "drop"
    for p in stale:
        p.unlink()
    for p in (PUB / "og").glob("*/*.png"):
        if not (PUB / "news" / p.parent.name / (p.stem + ".html")).exists():
            p.unlink()
    n_urls = sitemaps(days, items)
    n_feed = rss(items)
    n_search = write_search_index(items)
    ops = write_ops(days, items)
    write_api(days, items, ops)
    return (f"pages: {len(items)} articles + {len(days)} day pages; og images redrawn {made}; "
            f"sitemap {n_urls} urls; feed {n_feed} items; search-index {n_search}; "
            f"ops+api written" + (f"; removed {len(stale)} stale" if stale else ""))


if __name__ == "__main__":
    print(generate())
