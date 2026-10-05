#!/usr/bin/env python3
"""make_story_cards.py — static 1080x1920 Instagram story cards for نبض فردا (site style: #0b0c0f, accent #ff5a4e, Vazirmatn).
Rendered with headless Chrome (correct Persian shaping / bidi).

Usage: python3 make_story_cards.py spec.json OUT_DIR
spec.json: {"news":[{"id","date","headline","summary","category","source","image"}...], "promo": {...} | null}
headline may contain <em>..</em> to colour a phrase with the accent."""
import json, os, sys, html
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from make_insta import fetch_image, fa, file_url

FONTS = "/workspace/insta/assets/fonts"
CAT = {"ai": "هوش مصنوعی", "tech": "تکنولوژی", "game": "گیم"}
MARK = '<svg class="mark" viewBox="0 0 48 48"><path d="M3 26h9l4-10 7 20 6-26 5 16h11"/></svg>'
PLANE = '<svg class="ico" viewBox="0 0 24 24"><path d="M21.5 3.5 2.8 10.7c-.9.4-.9 1.6.1 1.9l4.6 1.5 1.8 5.6c.3.8 1.3 1 1.9.4l2.6-2.5 4.8 3.5c.7.5 1.6.1 1.8-.7l3-15c.2-1-.8-1.8-1.9-1.4Z"/><path d="m7.6 14.1 10.1-7.3-7.6 8.6"/></svg>'
ARROW = '<svg class="ico" viewBox="0 0 24 24"><path d="M19 12H5m6-6-6 6 6 6"/></svg>'
MOON = '<svg class="ico" viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg>'
BOLT = '<svg class="ico" viewBox="0 0 24 24"><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/></svg>'
GLOBE = '<svg class="ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z"/></svg>'

def font_css():
    w = {"Regular": 400, "Medium": 500, "Bold": 700, "ExtraBold": 800, "Black": 900}
    return "".join(f"@font-face{{font-family:Vazirmatn;src:url('{file_url(os.path.join(FONTS, f'Vazirmatn-{k}.ttf'))}');font-weight:{v}}}" for k, v in w.items())

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;overflow:hidden;background:#0b0c0f}
body{font-family:Vazirmatn,sans-serif;direction:rtl;color:#f2f2f3;-webkit-font-smoothing:antialiased;position:relative}
.ltr{direction:ltr;unicode-bidi:isolate}
.mark{width:58px;height:58px;fill:none;stroke:#ff5a4e;stroke-width:4;stroke-linecap:round;stroke-linejoin:round}
.ico{width:1em;height:1em;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.top{position:absolute;top:150px;left:84px;right:84px;display:flex;align-items:center;justify-content:space-between}
.brand{display:flex;align-items:center;gap:16px;font-weight:800;font-size:46px;letter-spacing:-.5px}
.date{font-size:30px;color:#8b8e97;font-weight:500}
.photo{position:absolute;top:268px;left:84px;right:84px;height:700px;border-radius:30px;background:#16181d center/cover no-repeat;
  box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.07)}
.meta{position:absolute;top:1034px;left:84px;right:84px;display:flex;align-items:center;gap:22px;font-size:32px}
.chip{display:inline-flex;align-items:center;gap:12px;padding:8px 24px 10px;border-radius:999px;border:2px solid rgba(255,90,78,.55);color:#ff5a4e;font-weight:700}
.chip:before{content:"";width:12px;height:12px;border-radius:50%;background:#ff5a4e}
.src{color:#8b8e97;font-weight:500}
.src b{color:#d6d7db;font-weight:700}
.hl{position:absolute;top:1118px;left:84px;right:84px;font-weight:900;font-size:76px;line-height:1.36;letter-spacing:-.5px;color:#fff}
.hl em{font-style:normal;color:#ff5a4e;white-space:nowrap}
.sum{margin-top:30px;font-weight:400;font-size:35px;line-height:1.75;color:#a2a5ae;letter-spacing:0}
.foot{position:absolute;left:84px;right:84px;bottom:220px;border-top:1.5px solid rgba(255,255,255,.09);padding-top:34px;display:flex;align-items:center;justify-content:space-between}
.cta{display:flex;align-items:center;gap:14px;font-size:33px;font-weight:700;color:#e9eaec}
.cta .ico{color:#ff5a4e;width:36px;height:36px}
.cta span.m{color:#6f727b;font-weight:500}
.url{font-size:28px;color:#6f727b;font-weight:500}
/* promo */
.p-wrap{position:absolute;top:280px;left:84px;right:84px}
.p-badge{width:124px;height:124px;border-radius:34px;background:#ff5a4e;display:flex;align-items:center;justify-content:center;color:#0b0c0f}
.p-badge .ico{width:68px;height:68px;stroke-width:1.8}
.p-kick{margin-top:56px;font-size:34px;font-weight:700;color:#ff5a4e}
.p-title{margin-top:14px;font-size:104px;font-weight:900;line-height:1.25;letter-spacing:-1px}
.p-sub{margin-top:34px;font-size:42px;line-height:1.7;color:#b4b6be;font-weight:500}
.p-list{margin-top:56px;border-top:1.5px solid rgba(255,255,255,.09)}
.p-row{display:flex;align-items:center;gap:30px;padding:28px 0;border-bottom:1.5px solid rgba(255,255,255,.09)}
.p-row .ic{width:84px;height:84px;border-radius:24px;background:#16181d;display:flex;align-items:center;justify-content:center;color:#ff5a4e;flex:none}
.p-row .ic .ico{width:40px;height:40px}
.p-row b{display:block;font-size:40px;font-weight:800}
.p-row small{display:block;margin-top:4px;font-size:30px;color:#8b8e97;font-weight:400}
.p-cta{position:absolute;left:84px;right:84px;bottom:230px;display:flex;align-items:center;justify-content:space-between}
.btn{display:inline-flex;align-items:center;gap:18px;background:#ff5a4e;color:#0b0c0f;font-weight:800;font-size:42px;padding:26px 46px 30px;border-radius:999px}
.btn .ico{width:42px;height:42px;stroke-width:2.2}
.handle{font-size:32px;color:#8b8e97;font-weight:500}
"""

def page(body):
    return f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{font_css()}{CSS}</style></head><body>{body}</body></html>'

def news_card(s):
    img = fetch_image(s["image"])
    if not img: raise SystemExit(f"no image for {s['id']}")
    src = html.escape(s["source"])
    return page(f"""
<div class="top"><div class="brand">{MARK}<span>نبض فردا</span></div><div class="date">{html.escape(s.get('date_label',''))}</div></div>
<div class="photo" style="background-image:url('{file_url(img)}')"></div>
<div class="meta"><span class="chip">{CAT[s['category']]}</span><span class="src">منبع: <b class="ltr">{src}</b></span></div>
<div class="hl">{s['headline']}<div class="sum">{html.escape(s.get('summary',''))}</div></div>
<div class="foot"><div class="cta">{ARROW}<span>خبر کامل در سایت</span><span class="m">/</span><span>لینک در بیو</span></div><div class="url ltr">nabz-farda.vercel.app</div></div>""")

def promo_card(p):
    handle = f'<span class="handle ltr">{html.escape(p["handle"])}</span>' if p.get("handle") else '<span class="handle">عضویت رایگان</span>'
    return page(f"""
<div class="top"><div class="brand">{MARK}<span>نبض فردا</span></div><div class="date">Telegram</div></div>
<div class="p-wrap">
  <div class="p-badge">{PLANE}</div>
  <div class="p-kick">همین حالا عضو شو</div>
  <div class="p-title">کانال تلگرام<br>نبض فردا</div>
  <div class="p-sub">خبرهای فوری، زودتر از همه؛<br>و هر شب خلاصهٔ مهم‌ترین خبرهای روز.</div>
  <div class="p-list">
    <div class="p-row"><div class="ic">{BOLT}</div><div><b>خبرهای فوری</b><small>همان لحظه که اتفاق می‌افتد</small></div></div>
    <div class="p-row"><div class="ic">{MOON}</div><div><b>خلاصهٔ هر شب</b><small>گلچین خبرهای گیم، تکنولوژی و هوش مصنوعی</small></div></div>
    <div class="p-row"><div class="ic">{GLOBE}</div><div><b>به فارسی، با منبع</b><small>لینک گزارش کامل کنار هر خبر</small></div></div>
  </div>
</div>
<div class="p-cta"><span class="btn">{PLANE}<span>{html.escape(p.get('cta','لینک در بیو'))}</span></span>{handle}</div>""")

def main():
    spec = json.load(open(sys.argv[1])); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    cards = [news_card(s) for s in spec["news"]] + ([promo_card(spec["promo"])] if spec.get("promo") else [])
    from playwright.sync_api import sync_playwright
    chrome = next((p for p in ["/usr/bin/google-chrome", "/usr/bin/chromium"] if os.path.exists(p)), None)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox", "--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": 1080, "height": 1920})
        for i, h in enumerate(cards, 1):
            hp = os.path.join(out, f".{i:02d}.html"); open(hp, "w").write(h)
            pg.goto(file_url(hp)); pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(400)
            over = pg.evaluate("""(()=>{const h=document.querySelector('.hl')||document.querySelector('.p-wrap');const f=document.querySelector('.foot')||document.querySelector('.p-cta');
               return h&&f? Math.round(h.getBoundingClientRect().bottom - f.getBoundingClientRect().top):null})()""")
            pg.screenshot(path=os.path.join(out, f"{i:02d}.png")); os.remove(hp)
            print(f"{i:02d}.png", "overlap" if over and over > -30 else "ok", over)
        b.close()

if __name__ == "__main__":
    main()
