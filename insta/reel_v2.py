"""reel_v2.py — motion-graphics Reel renderer for «نبض فردا» (style v2).

Pipeline: one HTML page holds every scene (hook, stories, outro, HUD). A deterministic JS
timeline R(t) sets every transform/opacity for time t (custom easing curves, no CSS animation
clocks), headless Chrome renders each frame (several workers in parallel), ffmpeg muxes the
JPEG frames with a self-synthesised 120 BPM track + whoosh/impact SFX (reel_audio.py).
All cuts land on beats.  Persian text is shaped by Chrome (HarfBuzz) with Vazirmatn.
"""
import base64, html, json, math, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "assets", "fonts")
FPS = 30
BPM = 120
BEAT = 60 / BPM
W, H = 1080, 1920
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
def fa(s): return str(s).translate(FA_DIGITS)
def esc(s): return html.escape(str(s), quote=True)
def file_url(p):
    import urllib.request
    return "file://" + urllib.request.pathname2url(os.path.abspath(p))

LOGO_PATH = "M3 26h9l4-10 7 20 6-26 5 16h11"
def logo_svg(i):
    return (f'<svg viewBox="0 0 48 48"><defs><linearGradient id="lg{i}" x1="0" x2="1"><stop offset="0" stop-color="#22d3ee"/>'
            f'<stop offset=".55" stop-color="#a78bfa"/><stop offset="1" stop-color="#fb7185"/></linearGradient></defs>'
            f'<path d="{LOGO_PATH}" fill="none" stroke="url(#lg{i})" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>')

# ------------------------------------------------------------------ assets
def prep_images(stories, build):
    """card image (<=1600px jpg) + pre-blurred, darkened background for each story."""
    from PIL import Image, ImageFilter, ImageEnhance
    os.makedirs(os.path.join(build, "img"), exist_ok=True)
    for k, s in enumerate(stories):
        s["_card"] = s["_blur"] = None
        p = s.get("_img")
        if not p: continue
        try:
            im = Image.open(p); im.load(); im = im.convert("RGB")
        except Exception:
            s["_card"] = p; continue   # let Chrome decode it (e.g. avif); CSS blur fallback
        if im.width > 1600: im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
        cp = os.path.join(build, "img", f"card_{k}.jpg"); im.save(cp, quality=92); s["_card"] = cp
        sm = im.copy(); sm.thumbnail((360, 360))
        # cover-crop to 9:16 then blur
        tw, th = 270, 480; sc = max(tw / sm.width, th / sm.height)
        sm = sm.resize((max(tw, round(sm.width * sc)), max(th, round(sm.height * sc))), Image.LANCZOS)
        l, t = (sm.width - tw) // 2, (sm.height - th) // 2
        sm = sm.crop((l, t, l + tw, t + th)).filter(ImageFilter.GaussianBlur(14))
        sm = ImageEnhance.Brightness(ImageEnhance.Color(sm).enhance(1.25)).enhance(0.55)
        bp = os.path.join(build, "img", f"blur_{k}.jpg"); sm.save(bp, quality=90); s["_blur"] = bp

def make_grain(build):
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(3)
    a = (rng.normal(128, 46, (256, 256))).clip(0, 255).astype("uint8")
    p = os.path.join(build, "img", "grain.png"); Image.fromarray(a, "L").save(p); return p

# ------------------------------------------------------------------ text helpers
LAT = re.compile(r"[A-Za-z0-9]")
def word_units(title):
    """split a Persian title into animation units; consecutive Latin tokens stay together
    (so 'Gears of War: E-Day' keeps its LTR order inside the RTL line)."""
    toks = title.split()
    units = []
    for tk in toks:
        if units and LAT.search(tk) and LAT.search(units[-1]):
            units[-1] += " " + tk
        else:
            units.append(tk)
    return units

def words_html(text, cls="w"):
    out = []
    for u in word_units(text):
        lat = " lat" if LAT.search(u) else ""
        out.append(f'<span class="{cls}{lat}"><span class="wi">{esc(u)}</span></span>')
    return " ".join(out)

# ------------------------------------------------------------------ HTML
CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;overflow:hidden;background:#07080d}
body{font-family:Vazirmatn,sans-serif;direction:rtl;color:#eef0f7;-webkit-font-smoothing:antialiased}
#stage{position:relative;width:1080px;height:1920px;overflow:hidden;background:#07080d}
.scene{position:absolute;inset:0;overflow:hidden;background:#07080d;display:none;transform-origin:50% 45%}
.abs{position:absolute}
.grid{position:absolute;inset:-90px;background-image:linear-gradient(rgba(255,255,255,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px);
  background-size:90px 90px;-webkit-mask-image:radial-gradient(closest-side at 50% 50%,#000 20%,transparent 100%)}
.glowA{position:absolute;width:1300px;height:1300px;border-radius:50%;background:radial-gradient(closest-side,rgba(139,92,246,.42),rgba(139,92,246,0))}
.glowB{position:absolute;width:1100px;height:1100px;border-radius:50%;background:radial-gradient(closest-side,rgba(34,211,238,.24),rgba(34,211,238,0))}
/* words (mask reveal) */
.w{display:inline-block;overflow:hidden;vertical-align:top;padding:.16em .06em .34em;margin:-.16em -.06em -.34em}
.wi{display:inline-block;will-change:transform}
.lat .wi{color:var(--hl,#c4b5fd)}
/* ---------- HUD */
#hud{position:absolute;left:70px;right:70px;top:262px;height:100px;z-index:50}
.hb{position:absolute;right:0;top:0;display:flex;align-items:center;gap:14px}
.hb .mk{width:56px;height:56px;border-radius:16px;background:#121524;border:1px solid rgba(255,255,255,.12);display:grid;place-items:center}
.hb .mk svg{width:70%;height:70%}
.hb b{font-size:32px;font-weight:900;color:#fff;letter-spacing:-.2px}
.cnt{position:absolute;left:0;top:4px;height:50px;display:flex;align-items:center;gap:8px;font-weight:800;color:#9aa1b5;font-size:28px}
.cnt .cw{display:inline-block;overflow:hidden;height:50px;line-height:50px;padding:0 2px}
.cnt .cn{display:inline-block;color:#fff;font-size:40px;font-weight:900}
.cnt .lbl{font-size:24px;font-weight:700;color:#7c8299;margin-inline-end:6px}
.prog{position:absolute;left:0;right:0;top:80px;height:6px;display:flex;gap:10px}
.prog .sg{flex:1;height:6px;border-radius:3px;background:rgba(255,255,255,.16);overflow:hidden;transform-origin:100% 50%}
.prog .fl{height:100%;width:100%;background:linear-gradient(270deg,#22d3ee,#a78bfa);transform-origin:100% 50%;transform:scaleX(0)}
/* ---------- hook */
.hk-mq{position:absolute;left:-200px;top:420px;display:flex;gap:26px;direction:ltr;transform-origin:50% 50%}
.hk-mq div{width:330px;height:220px;border-radius:24px;background:#141725 center/cover no-repeat;flex:none;box-shadow:0 0 0 1px rgba(255,255,255,.08)}
.hk-shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,.15) 0,rgba(7,8,13,.35) 26%,rgba(7,8,13,.92) 38%,#07080d 60%)}
.hk-kick{position:absolute;top:630px;left:0;right:0;text-align:center}
.hk-kick span{display:inline-flex;align-items:center;gap:14px;font-size:32px;font-weight:800;color:#d9dcf0;padding:10px 28px 12px;border-radius:99px;background:rgba(255,255,255,.06);border:1.5px solid rgba(255,255,255,.14)}
.hk-kick i{width:14px;height:14px;border-radius:50%;background:#f43f5e;box-shadow:0 0 0 6px rgba(244,63,94,.22)}
.hk-num{position:absolute;top:740px;left:0;right:0;height:440px;text-align:center;font-size:430px;line-height:440px;font-weight:900}
.hk-num .g{display:inline-block;background:linear-gradient(160deg,#ffffff 15%,#c4b5fd 52%,#22d3ee 95%);-webkit-background-clip:text;background-clip:text;color:transparent}
.hk-num .o{position:absolute;left:0;right:0;top:0;color:transparent;-webkit-text-stroke:3px rgba(167,139,250,.55)}
.hk-title{position:absolute;top:1170px;left:60px;right:60px;text-align:center;font-size:122px;line-height:1.3;font-weight:900;color:#fff;letter-spacing:-1px}
.hk-date{position:absolute;top:1352px;left:0;right:0;text-align:center;font-size:40px;font-weight:700;color:#aab0c4}
.hk-chips{position:absolute;top:1440px;left:0;right:0;display:flex;justify-content:center;gap:16px}
.chip{display:inline-flex;align-items:center;gap:12px;font-size:30px;font-weight:800;padding:8px 26px 11px;border-radius:99px;color:var(--c);
  background:color-mix(in srgb,var(--c) 14%,rgba(7,8,13,.65));border:1.5px solid color-mix(in srgb,var(--c) 55%,transparent);white-space:nowrap}
.chip i{width:12px;height:12px;border-radius:50%;background:var(--c)}
.hk-line{position:absolute;height:2px;width:300px;background:linear-gradient(90deg,transparent,#a78bfa)}
.sweep{position:absolute;top:-30%;bottom:-30%;width:260px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.14),rgba(255,255,255,0));transform:skewX(-16deg);pointer-events:none}
/* ---------- story */
.sbg{position:absolute;inset:-80px}
.sbg img{width:100%;height:100%;object-fit:cover}
.tint{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,.62) 0,rgba(7,8,13,.25) 22%,rgba(7,8,13,.55) 46%,rgba(7,8,13,.94) 60%,#07080d 82%),
  radial-gradient(760px 560px at 88% 64%,color-mix(in srgb,var(--c) 26%,transparent),transparent 70%)}
.ring{position:absolute;left:-230px;top:560px;width:520px;height:520px;border-radius:50%;border:2px solid color-mix(in srgb,var(--c) 45%,transparent)}
.ring:after{content:"";position:absolute;left:50%;top:-7px;width:12px;height:12px;border-radius:50%;background:var(--c)}
.dots{position:absolute;left:84px;top:1030px;width:150px;height:60px;background-image:radial-gradient(circle,rgba(255,255,255,.35) 2px,transparent 2.5px);background-size:25px 25px}
.card{position:absolute;left:60px;top:410px;width:960px;height:590px;border-radius:34px;overflow:hidden;background:#11131d;
  box-shadow:0 40px 90px -24px rgba(0,0,0,.9),0 0 0 1.5px rgba(255,255,255,.10)}
.kb{position:absolute;inset:0}
.kb img{width:100%;height:100%;object-fit:cover}
.cshade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,0) 55%,rgba(7,8,13,.5))}
.brk{position:absolute;width:64px;height:64px;border:0 solid var(--c)}
.brk.a{left:36px;top:386px;border-width:4px 0 0 4px;border-top-left-radius:18px}
.brk.b{right:36px;top:950px;border-width:0 4px 4px 0;border-bottom-right-radius:18px}
.badge{position:absolute;right:140px;top:938px;width:128px;height:128px;border-radius:32px;background:var(--c);color:#07080d;
  display:flex;align-items:center;justify-content:center;font-size:88px;font-weight:900;line-height:1;box-shadow:0 20px 44px -12px rgba(0,0,0,.8);z-index:3}
.badge span{display:block;margin-top:-8px}
.meta{position:absolute;right:140px;left:70px;top:1104px;display:flex;align-items:center;justify-content:space-between}
.src{font-size:25px;font-weight:700;color:#8f96ab}
.src b{color:#d6d9e6;font-weight:800}
.title{position:absolute;right:140px;left:70px;top:1186px;font-size:70px;line-height:1.48;font-weight:900;color:#fff;text-align:right}
.uline{position:absolute;right:140px;height:6px;width:240px;border-radius:3px;background:linear-gradient(270deg,var(--c),rgba(167,139,250,0));transform-origin:100% 50%}
.plus{position:absolute;width:26px;height:26px}
.plus:before,.plus:after{content:"";position:absolute;background:rgba(255,255,255,.5)}
.plus:before{left:12px;top:0;width:2px;height:26px}.plus:after{top:12px;left:0;height:2px;width:26px}
/* ---------- outro */
.o-pulse{position:absolute;left:-40px;right:-40px;top:520px;height:300px}
.o-mark{position:absolute;left:50%;top:560px;width:200px;height:200px;margin-left:-100px;border-radius:56px;background:#121524;border:1.5px solid rgba(255,255,255,.12);display:grid;place-items:center;
  box-shadow:0 30px 80px -20px rgba(0,0,0,.9),0 0 0 10px rgba(167,139,250,.07)}
.o-mark svg{width:70%;height:70%}
.o-name{position:absolute;top:812px;left:60px;right:60px;text-align:center;font-size:150px;line-height:1.3;font-weight:900}
.o-name .wi{background:linear-gradient(160deg,#fff 20%,#c4b5fd 60%,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent}
.o-tag{position:absolute;top:1035px;left:140px;right:140px;text-align:center;font-size:33px;font-weight:600;color:#a3a9bd;line-height:1.7}
.o-btn{position:absolute;top:1190px;left:0;right:0;text-align:center}
.o-btn span{position:relative;display:inline-flex;align-items:center;gap:16px;font-size:50px;font-weight:900;color:#07080d;padding:18px 56px 24px;border-radius:99px;background:linear-gradient(120deg,#a78bfa,#22d3ee)}
.o-btn svg{width:46px;height:46px;fill:none;stroke:#07080d;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
.o-btn .rg{position:absolute;inset:0;border-radius:99px;border:3px solid #a78bfa}
.o-url{position:absolute;top:1360px;left:0;right:0;text-align:center}
.o-url span{display:inline-block;direction:ltr;font-size:42px;font-weight:800;letter-spacing:.5px;color:#e6e8f2;padding:14px 36px 18px;border-radius:24px;background:rgba(255,255,255,.05);border:1.5px solid rgba(167,139,250,.45)}
/* ---------- single-story mode (--single): hook question + one story with summary */
.hs-bg{position:absolute;inset:-60px}
.hs-bg img{width:100%;height:100%;object-fit:cover}
.hs-shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(7,8,13,.7) 0,rgba(7,8,13,.38) 22%,rgba(7,8,13,.66) 50%,rgba(7,8,13,.94) 74%),
  radial-gradient(900px 700px at 85% 40%,color-mix(in srgb,var(--c) 22%,transparent),transparent 70%)}
.hs-kick{position:absolute;top:610px;left:0;right:0;text-align:center}
.hs-kick span{display:inline-flex;align-items:center;gap:14px;font-size:34px;font-weight:800;color:#e4e6f2;padding:10px 30px 13px;border-radius:99px;background:rgba(7,8,13,.55);border:1.5px solid color-mix(in srgb,var(--c) 60%,transparent)}
.hs-kick i{width:14px;height:14px;border-radius:50%;background:#f43f5e;box-shadow:0 0 0 6px rgba(244,63,94,.22)}
.hs-q{position:absolute;top:730px;left:90px;right:90px;text-align:center;font-size:104px;line-height:1.42;font-weight:900;color:#fff;letter-spacing:-.5px;text-shadow:0 6px 40px rgba(0,0,0,.55)}
.hs-q .hl .wi{color:var(--c)}
.hk-title .hl .wi{background:linear-gradient(160deg,#fff 10%,#c4b5fd 55%,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent}
.hs-sub{position:absolute;left:0;right:0;text-align:center;font-size:38px;font-weight:700;color:#b9bed0}
.hs-sub b{color:#fff;font-weight:900}
.hs-bar{position:absolute;left:50%;width:120px;height:6px;margin-left:-60px;border-radius:3px;background:var(--c)}
#stage.single .cnt{display:none}
#stage.withsum .card{top:370px;height:500px}
#stage.withsum .brk.a{top:346px}
#stage.withsum .brk.b{top:820px}
#stage.withsum .badge,#stage.withsum .dots{display:none}
#stage.withsum .meta{top:918px}
#stage.withsum .title{top:992px;font-size:68px}
#stage.withsum .ring{top:500px}
.sum{position:absolute;right:140px;left:70px;font-size:36px;line-height:1.62;font-weight:500;color:#cfd3e0;text-align:right}
.sum b{color:#fff;font-weight:800}
#flash{position:absolute;inset:0;background:#f4f0ff;opacity:0;z-index:80;pointer-events:none}
#grain{position:absolute;inset:-128px;opacity:.075;mix-blend-mode:overlay;z-index:90;pointer-events:none}
#vig{position:absolute;inset:0;z-index:85;pointer-events:none;background:radial-gradient(140% 90% at 50% 45%,transparent 55%,rgba(0,0,0,.45))}
"""

FOLLOW_ICO = '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-6.5 7-6.5s7 2.5 7 6.5M19 8v6M16 11h6"/></svg>'

def hook_words_html(text):
    """words for the single-mode hook; *word* (or *several words*) = highlighted in the category colour."""
    out = []
    for k, part in enumerate(re.split(r"\*", text)):
        if not part.strip(): continue
        h = words_html(part.strip())
        out.append(re.sub(r'class="w( lat)?"', r'class="w hl\1"', h) if k % 2 else h)
    return " ".join(out)

def build_html(stories, cats, texts, timeline, grain, out_html, single=None, withsum=False):
    withsum = withsum or bool(single)
    n = len(stories)
    faces = "".join(
        f"@font-face{{font-family:Vazirmatn;src:url('{file_url(os.path.join(FONT_DIR, f'Vazirmatn-{nm}.ttf'))}') format('truetype');font-weight:{wg};font-display:block}}"
        for nm, wg in [("Regular", 400), ("Medium", 500), ("Bold", 700), ("ExtraBold", 800), ("Black", 900)])
    filters = "".join(
        f'<filter id="fb{k}" x="-25%" y="-25%" width="150%" height="150%" color-interpolation-filters="sRGB"><feGaussianBlur id="fbg{k}" stdDeviation="0 0"/></filter>'
        f'<filter id="fg{k}" x="-5%" y="0" width="110%" height="100%" color-interpolation-filters="sRGB">'
        f'<feOffset id="fgr{k}" in="SourceGraphic" dx="0" result="r0"/><feColorMatrix in="r0" type="matrix" values="1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0" result="r"/>'
        f'<feOffset id="fgb{k}" in="SourceGraphic" dx="0" result="b0"/><feColorMatrix in="b0" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 1 0" result="b"/>'
        f'<feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 1 0" result="g"/>'
        f'<feComposite in="r" in2="g" operator="arithmetic" k2="1" k3="1" result="rg"/><feComposite in="rg" in2="b" operator="arithmetic" k2="1" k3="1"/></filter>'
        for k in range(n + 2))
    # ---- hook
    thumbs = [s["_card"] for s in stories if s.get("_card")] or [""]
    row = (thumbs * 4)[:10]
    mq = "".join(f'<div style="background-image:url(\'{file_url(t)}\')"></div>' if t else "<div></div>" for t in row)
    chip_html = "".join(f'<span class="chip hc" style="--c:{cats[c][1]}"><i></i>{cats[c][0]}</span>'
                        for c in cats if any(s["category"] == c for s in stories))
    hook = f"""<div class="scene" id="sc0">
  <div class="glowA" style="left:200px;top:-300px"></div><div class="glowB" style="left:-500px;top:900px"></div><div class="grid"></div>
  <div class="hk-mq" id="mq">{mq}</div><div class="hk-shade"></div>
  <div class="hk-line" id="hl1" style="left:70px;top:1342px"></div><div class="hk-line" id="hl2" style="right:70px;top:1342px;transform:scaleX(-1)"></div>
  <div class="hk-kick" id="hkk"><span><i></i>{esc(texts['kick'])}</span></div>
  <div class="hk-num"><span class="o" id="hno">{fa(n)}</span><span class="g" id="hn">{fa(n)}</span></div>
  <div class="hk-title" id="hkt">{hook_words_html(texts['hook'])}</div>
  <div class="hk-date" id="hkd">{esc(texts['date'])}</div>
  <div class="hk-chips">{chip_html}</div>
  <div class="sweep" id="hsw" style="top:700px;bottom:auto;height:700px"></div>
</div>"""
    # ---- stories
    if single:
        s0 = stories[0]; lab, col = cats.get(s0["category"], ["خبر", "#a78bfa"])
        bgimg = f'<img src="{file_url(s0["_card"])}">' if s0.get("_card") else ""
        hook = f"""<div class="scene" id="sc0" style="--c:{col};--hl:color-mix(in srgb,{col} 55%,#fff)">
  <div class="hs-bg" id="hsbg">{bgimg}</div><div class="hs-shade"></div><div class="grid" style="opacity:.55"></div>
  <div class="glowA" style="left:200px;top:-300px;opacity:.6"></div>
  <div class="hs-kick" id="hkk"><span><i></i>{esc(single.get('kick') or lab)}</span></div>
  <h1 class="hs-q" id="hkt">{hook_words_html(single['hook'])}</h1>
  <div class="hs-bar" id="hsb"></div>
  <div class="hs-sub" id="hss">{esc(single.get('sub', ''))}</div>
  <div class="sweep" id="hsw" style="top:640px;bottom:auto;height:760px"></div>
</div>"""
    sc = []
    for i, s in enumerate(stories):
        lab, col = cats.get(s["category"], ["خبر", "#a78bfa"])
        card = f'<img src="{file_url(s["_card"])}">' if s.get("_card") else ""
        if s.get("_blur"): bg = f'<img src="{file_url(s["_blur"])}">'
        elif s.get("_card"): bg = f'<img src="{file_url(s["_card"])}" style="filter:blur(40px) brightness(.5)">'
        else: bg = f'<div style="position:absolute;inset:0;background:radial-gradient(600px 500px at 60% 30%,{col}55,#0d0f17)"></div>'
        sc.append(f"""<div class="scene story" id="sc{i+1}" style="--c:{col};--hl:color-mix(in srgb,{col} 55%,#fff)">
  <div class="sbg">{bg}</div><div class="tint"></div><div class="grid" style="opacity:.5"></div>
  <div class="ring"></div><div class="plus" style="left:930px;top:1500px"></div><div class="plus" style="left:110px;top:1500px;opacity:.6"></div>
  <div class="card"><div class="kb">{card}</div><div class="cshade"></div><div class="sweep"></div></div>
  <div class="brk a"></div><div class="brk b"></div>
  <div class="dots"></div>
  <div class="badge"><span>{fa(i+1)}</span></div>
  <div class="meta"><span class="chip" style="--c:{col}"><i></i>{lab}</span><span class="src">منبع: <b><bdi>{esc(s.get('source',''))}</bdi></b></span></div>
  <h1 class="title">{words_html(s['title_fa'])}</h1>
  <div class="uline"></div>{('<p class="sum">' + " ".join(f'<span class="wi">{esc(u)}</span>' for u in word_units(s.get("_sum", ""))) + '</p>') if withsum else ''}
</div>""")
    # ---- outro
    k = n + 1
    outro = f"""<div class="scene" id="sc{k}">
  <div class="glowA" style="left:-100px;top:200px"></div><div class="glowB" style="left:300px;top:1000px"></div><div class="grid"></div>
  <svg class="o-pulse" viewBox="0 0 1160 300" preserveAspectRatio="none"><path id="opl" d="M0 150h330l50-100 80 210 70-230 60 170 50-50h520"
    fill="none" stroke="#a78bfa" stroke-opacity=".35" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/></svg>
  <div class="o-mark" id="omk">{logo_svg(99)}</div>
  <div class="o-name" id="onm">{words_html("نبض فردا")}</div>
  <div class="o-tag" id="otg">{esc(texts['tag']).replace(chr(10), '<br>')}</div>
  <div class="o-btn" id="obt"><span><i class="rg" id="org"></i>{FOLLOW_ICO}دنبال کن</span></div>
  <div class="o-url" id="ourl"><span>{texts['url']}</span></div>
</div>"""
    segs = "".join('<div class="sg"><div class="fl"></div></div>' for _ in stories)
    hud = f"""<div id="hud"><div class="hb"><span class="mk">{logo_svg(98)}</span><b>نبض فردا</b></div>
  <div class="cnt"><span class="lbl">خبر</span><span class="cw"><span class="cn" id="cn">{fa(1)}</span></span><span>/ {fa(n)}</span></div>
  <div class="prog" id="prog">{segs}</div></div>"""
    page = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{faces}{CSS}</style></head><body>
<svg width="0" height="0" style="position:absolute"><defs>{filters}</defs></svg>
<div id="stage" class="{'single ' if single else ''}{'withsum' if withsum else ''}">{hook}{''.join(sc)}{outro}{hud}<div id="vig"></div><div id="flash"></div><div id="grain" style="background-image:url('{file_url(grain)}')"></div></div>
<script>window.CFG={json.dumps(timeline)};</script><script>{JS}</script></body></html>"""
    open(out_html, "w", encoding="utf-8").write(page)

# ------------------------------------------------------------------ timeline JS
JS = r"""
const C=window.CFG, B=C.beat;
const cl=x=>Math.max(0,Math.min(1,x)), lerp=(a,b,p)=>a+(b-a)*p, sg=(t,a,d)=>cl((t-a)/d);
const oc=x=>1-Math.pow(1-x,3), ic=x=>x*x*x, oq=x=>1-Math.pow(1-x,5), oe=x=>x>=1?1:1-Math.pow(2,-10*x),
      io=x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2, ios=x=>-(Math.cos(Math.PI*x)-1)/2,
      ob=x=>{const c1=1.9,c3=c1+1;return 1+c3*Math.pow(x-1,3)+c1*Math.pow(x-1,2)}, ie=x=>x<=0?0:Math.pow(2,10*x-10);
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const S=C.scenes.map((sc,k)=>({...sc,el:document.getElementById('sc'+k),k}));
function beatPulse(t){const p=((t%B)+B)%B;return Math.exp(-p*9)}
function rnd(i){const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x)}
// ---------- setup: fit titles, collect nodes
function setup(){
  for(const s of S){
    s.words=$$('.title .wi,.hk-title .wi,.hs-q .wi,.o-name .wi',s.el);
    if(s.type==='story'){
      const h=$('.title',s.el); let fs=parseFloat(getComputedStyle(h).fontSize);
      const lines=()=>Math.round(h.getBoundingClientRect().height/(fs*1.48));
      s.el.style.display='block';
      while(lines()>3&&fs>50){fs-=2;h.style.fontSize=fs+'px'}
      const r=h.getBoundingClientRect(); s.nlines=lines();
      $('.uline',s.el).style.top=(r.bottom+26)+'px';
      const sm=$('.sum',s.el);
      if(sm){ sm.style.top=(r.bottom+58)+'px'; let f2=36;
        while(sm.getBoundingClientRect().bottom>1488&&f2>28){f2-=1;sm.style.fontSize=f2+'px'} s.sum=sm; s.sumw=$$('.wi',sm); }
      s.el.style.display='none';
      s.n={card:$('.card',s.el),kb:$('.kb',s.el),sbg:$('.sbg',s.el),sw:$('.sweep',s.el),ring:$('.ring',s.el),badge:$('.badge',s.el),
        chip:$('.chip',s.el),src:$('.src',s.el),ul:$('.uline',s.el),ba:$('.brk.a',s.el),bb:$('.brk.b',s.el),dots:$('.dots',s.el),plus:$$('.plus',s.el)};
    }
  }
  const p=document.getElementById('opl'); window.PL=p.getTotalLength(); p.style.strokeDasharray=PL;
}
function words(ws,lt,start,stag,dur,dist){
  ws.forEach((w,i)=>{const p=oq(sg(lt,start+i*stag,dur));w.style.transform=`translateY(${(1-p)*dist}%) rotate(${(1-p)*3}deg)`;w.style.visibility=p<=0?'hidden':'visible';});
}
// ---------- per-scene animation (lt = local time)
function animHook(s,lt0,t){ const lt=lt0*(C.spd||1);
  const mq=$('#mq'); mq.style.transform=`rotate(-7deg) translateX(${-lt*240+40}px) scale(${lerp(1.15,1,oe(sg(lt,0,.8)))})`;
  mq.style.opacity=.75*sg(lt,0,.25);
  const pn=oe(sg(lt,0,.42)), bp=lt>.45?beatPulse(lt):0;
  const hn=$('#hn'), ho=$('#hno');
  hn.style.transform=`scale(${lerp(2.1,1,pn)*(1+.05*bp)})`; hn.style.filter=`blur(${lerp(9,0,pn)}px)`; hn.style.opacity=lerp(.55,1,sg(lt,0,.12));
  const po=oe(sg(lt,.08,.6)); ho.style.transform=`translate(${lerp(-60,26,po)}px,${lerp(-40,18,po)}px) scale(${lerp(1.6,1,po)})`; ho.style.opacity=.9*sg(lt,.08,.2);
  const kk=oc(sg(lt,.12,.4)); $('#hkk').style.transform=`translateY(${(1-kk)*-30}px)`; $('#hkk').style.opacity=kk;
  words(s.words,lt,.22,.09,.5,140);
  const d=sg(lt,.62,.45); $('#hkd').style.clipPath=`inset(0 ${(1-oc(d))*50}% 0 ${(1-oc(d))*50}%)`;
  $$('.hc').forEach((c,i)=>{const p=sg(lt,.78+i*.1,.38);c.style.transform=`scale(${ob(p)})`;c.style.opacity=cl(p*3)});
  const l=oe(sg(lt,.5,.6)); $('#hl1').style.transform=`scaleX(${l})`; $('#hl1').style.transformOrigin='100% 50%'; $('#hl2').style.transform=`scaleX(${-l})`;$('#hl2').style.transformOrigin='100% 50%';
  const w=sg(lt,1.05,.6); $('#hsw').style.transform=`translateX(${lerp(1200,-400,io(w))}px) skewX(-16deg)`; $('#hsw').style.opacity=w>0&&w<1?1:0;
  const g=$$('.glowA,.glowB',s.el); g[0].style.transform=`translate(${Math.sin(lt*1.3)*60}px,${Math.cos(lt)*40}px)`;g[1].style.transform=`translate(${Math.cos(lt*1.1)*60}px,${Math.sin(lt*.9)*50}px)`;
}
function animHookS(s,lt,t){
  // single-story hook: the question is readable inside the first second
  const bg=$('#hsbg'); bg.style.transform=`scale(${lerp(1.32,1.12,ios(cl(lt/s.end)))}) translateY(${lerp(0,-40,cl(lt/s.end))}px)`;
  bg.style.opacity=lerp(.35,1,oc(sg(lt,0,.5)));
  const kk=oc(sg(lt,0,.3)); $('#hkk').style.transform=`translateY(${(1-kk)*-26}px) scale(${lerp(.9,1,kk)})`; $('#hkk').style.opacity=kk;
  words(s.words,lt,.03,.045,.38,120);
  const q=$('#hkt'), bp=lt>1.2?beatPulse(t):0; q.style.transform=`scale(${(1+.012*bp)*lerp(1.04,1,oe(sg(lt,0,.9)))})`;
  if(!s.qb){s.qb=q.getBoundingClientRect().bottom; $('#hsb').style.top=(s.qb+34)+'px'; $('#hss').style.top=(s.qb+70)+'px';}
  const b=oe(sg(lt,.45+s.words.length*.045,.5)); $('#hsb').style.transform=`scaleX(${b})`;
  const su=oc(sg(lt,.65+s.words.length*.045,.45)); $('#hss').style.opacity=su; $('#hss').style.transform=`translateY(${(1-su)*24}px)`;
  const w=sg(lt,1.0,.7); $('#hsw').style.transform=`translateX(${lerp(1200,-400,io(w))}px) skewX(-16deg)`; $('#hsw').style.opacity=w>0&&w<1?1:0;
  const g=$('.glowA',s.el); g.style.transform=`translate(${Math.sin(lt*1.3)*60}px,${Math.cos(lt)*40}px)`;
}
function animStory(s,lt0,t){ const lt=lt0*(C.spd||1), KB=C.kb||1;
  const n=s.n, D=s.dur, u=cl(lt0/D), dir=s.i%2?1:-1;
  n.sbg.style.transform=`scale(1.18) translate(${dir*lerp(-30,30,u)*KB}px,${lerp(30,-20,u)*KB}px)`;
  const ce=oq(sg(lt,0,.7));
  n.card.style.transform=`translateY(${lerp(80,0,ce)-u*14}px) scale(${lerp(.9,1,ce)}) rotate(${lerp(dir*-3,0,ce)}deg)`;
  n.kb.style.transform=`scale(${lerp(1.06,1.06+.16*KB,ios(u))}) translate(${dir*lerp(-22,22,ios(u))*KB}px,${lerp(10,-14,u)*KB}px)`;
  const sw=sg(lt,.75,.7); n.sw.style.transform=`translateX(${lerp(1100,-380,io(sw))}px) skewX(-16deg)`; n.sw.style.opacity=sw>0&&sw<1?1:0;
  const br=oe(sg(lt,.3,.55)); n.ba.style.transform=`translate(${(1-br)*40}px,${(1-br)*40}px)`; n.ba.style.opacity=br; n.bb.style.transform=`translate(${(1-br)*-40}px,${(1-br)*-40}px)`; n.bb.style.opacity=br;
  const rg=oe(sg(lt,.1,.9)); n.ring.style.transform=`scale(${lerp(.5,1,rg)}) rotate(${lt*28+s.i*60}deg)`; n.ring.style.opacity=rg*.9;
  n.dots.style.opacity=sg(lt,.5,.4)*.8; n.dots.style.transform=`translateX(${lerp(-30,0,oc(sg(lt,.5,.6)))}px)`;
  n.plus.forEach((p,j)=>{const q=oe(sg(lt,.6+j*.15,.5));p.style.transform=`rotate(${(1-q)*-180+lt*20}deg) scale(${q})`;});
  const bp=beatPulse(t)*(lt>.8?1:0);
  const b=sg(lt,.28,.5); n.badge.style.transform=`scale(${ob(b)*(1+.06*bp)}) rotate(${lerp(-24,0,oq(b))}deg)`; n.badge.style.opacity=cl(b*4);
  const c=sg(lt,.42,.42); n.chip.style.transform=`scale(${ob(c)})`; n.chip.style.opacity=cl(c*4); n.chip.style.transformOrigin='100% 50%';
  const sr=oc(sg(lt,.55,.45)); n.src.style.transform=`translateX(${(1-sr)*-50}px)`; n.src.style.opacity=sr;
  words(s.words,lt,.45,.055,.55,120);
  const ul=oe(sg(lt,.45+s.words.length*.055+.05,.7)); n.ul.style.transform=`scaleX(${ul})`;
  if(s.sum){ const t0=.75+s.words.length*.055; const sp=oc(sg(lt,t0,.6)); s.sum.style.opacity=sp; s.sum.style.transform=`translateY(${(1-sp)*30}px)`;
    s.sumw.forEach((w,i)=>{const p=oc(sg(lt,t0+i*.03,.4)); w.style.opacity=p;}); }
}
function animOutro(s,lt0,t){ const lt=lt0*(C.spd||1);
  const D=s.dur; $('#onm').style.opacity=1; $('#ourl').style.opacity=1;
  $('#opl').style.strokeDashoffset=PL*(1-oe(sg(lt,0,.9)));
  const m=sg(lt,.1,.5); $('#omk').style.transform=`scale(${ob(m)}) rotate(${lerp(-30,0,oq(m))}deg)`; $('#omk').style.opacity=cl(m*4);
  words(s.words,lt,.3,.12,.55,115);
  const tg=oc(sg(lt,.62,.45)); $('#otg').style.transform=`translateY(${(1-tg)*30}px)`; $('#otg').style.opacity=tg;
  const bt=sg(lt,.85,.5), bp=lt>1.3&&lt0<D-.5?beatPulse(t):0; $('#obt').style.transform=`scale(${ob(bt)*(1+.04*bp)})`; $('#obt').style.opacity=cl(bt*4);
  const ph=((t%B)+B)%B/B; const rg=$('#org'); rg.style.transform=`scale(${1+ph*.35},${1+ph*.8})`; rg.style.opacity=lt>1.3&&lt0<D-.5?(1-ph)*.7:0;
  const ur=oc(sg(lt,1.15,.5)); $('#ourl').style.clipPath=`inset(0 ${(1-ur)*50}% 0 ${(1-ur)*50}%)`; $('#ourl').style.transform=`translateY(${(1-ur)*20}px)`;
  const g=$$('.glowA,.glowB',s.el); g[0].style.transform=`translate(${Math.sin(lt*1.3)*60}px,${Math.cos(lt)*40}px)`;g[1].style.transform=`translate(${Math.cos(lt*1.1)*60}px,${Math.sin(lt*.9)*50}px)`;
  // loop-friendly end: everything settles back into the dark background
  const e=oc(sg(lt0,D-.42,.4));
  g[0].style.transform+=` translate(${300*e}px,${-500*e}px)`; g[1].style.transform+=` translate(${-800*e}px,${-100*e}px)`; $('#opl').style.opacity=1-e*.85; for(const id of ['omk','onm','otg','obt','ourl']){const el=document.getElementById(id); el.style.opacity=(parseFloat(el.style.opacity||1))*(1-e);}
  $('#onm').style.transform=`scale(${1-.06*e})`;
}
// ---------- transitions
function setT(s,o){
  const el=s.el, k=s.k;
  el.style.transform=`translate(${o.tx||0}px,${o.ty||0}px) scale(${o.s||1}) skewX(${o.sk||0}deg)`;
  el.style.opacity=o.op==null?1:o.op;
  if(o.bx||o.by){document.getElementById('fbg'+k).setAttribute('stdDeviation',`${o.bx||0} ${o.by||0}`);el.style.filter=`url(#fb${k})`;}
  else if(o.rgb){document.getElementById('fgr'+k).setAttribute('dx',o.rgb);document.getElementById('fgb'+k).setAttribute('dx',-o.rgb);el.style.filter=`url(#fg${k})`;}
  else el.style.filter='none';
}
function trans(type,p,f){ // p in [0,1] across the cut window; returns [outState,inState,flash,inOnTop]
  switch(type){
    case 'zoom':{const a=ic(cl(p/.5)), b=oe(cl((p-.45)/.55));
      return [{s:1+.7*a,op:1-a,bx:12*a,by:12*a},{s:lerp(.82,1,b),op:cl((p-.42)/.12),bx:(1-b)*10,by:(1-b)*10},.12*Math.exp(-Math.pow((p-.5)/.1,2)),p>.45];}
    case 'whip':{const x=io(p), bl=90*Math.sin(Math.PI*p);
      return [{tx:-1080*x,bx:bl},{tx:1080*(1-x),bx:bl},0,true];}
    case 'whipR':{const x=io(p), bl=90*Math.sin(Math.PI*p);
      return [{tx:1080*x,bx:bl},{tx:-1080*(1-x),bx:bl},0,true];}
    case 'push':{const x=io(p), bl=70*Math.sin(Math.PI*p);
      return [{ty:-1920*x,by:bl,s:1-.08*Math.sin(Math.PI*p)},{ty:1920*(1-x),by:bl,s:1-.08*Math.sin(Math.PI*p)},0,true];}
    case 'glitch':{const j=(rnd(f)-.5), a=Math.sin(Math.PI*p);
      return [{tx:j*80*a,rgb:16*a,sk:j*5*a,s:1+.04*a},{tx:-j*80*a,rgb:16*a,sk:-j*5*a,s:1+.04*a},(f%3===0?.06:0)*a,p>=.5];}
    case 'flash':{const a=cl(p/.5), b=oe(cl((p-.5)/.5));
      return [{s:1+.1*ic(a)},{s:lerp(1.14,1,b)},.55*Math.exp(-Math.pow((p-.5)/.1,2)),p>=.5];}
  }
}
function R(t,f){
  const TW=C.tw; let flash=0;
  for(const s of S){s.vis=false}
  // which scenes are visible
  for(const s of S){
    if(t>=s.start-TW*C.pre && t<s.end+TW*(1-C.pre)) s.vis=true;
  }
  for(const s of S){ s.el.style.display=s.vis?'block':'none'; if(s.vis){setT(s,{});s.el.style.zIndex=1;} }
  // transitions
  for(let k=0;k<S.length-1;k++){
    const cut=S[k].end, a=cut-TW*C.pre;
    if(t>=a && t<a+TW){
      const p=(t-a)/TW, [o,i,fl,top]=trans(C.cuts[k],p,f);
      setT(S[k],o); setT(S[k+1],i); flash=Math.max(flash,fl);
      S[k].el.style.zIndex=top?1:2; S[k+1].el.style.zIndex=top?2:1;
    }
  }
  for(const s of S){ if(!s.vis) continue; const lt=t-s.start;
    if(s.type==='hook')animHook(s,lt,t); else if(s.type==='hookS')animHookS(s,lt,t); else if(s.type==='story')animStory(s,Math.max(lt,0),t); else animOutro(s,Math.max(lt,0),t); }
  // HUD
  const hud=document.getElementById('hud'), st=S.filter(s=>s.type==='story'), oS=S[S.length-1].start;
  const hin=oc(sg(t,.35,.5)), hout=sg(t,oS-.15,.3);
  hud.style.opacity=hin*(1-hout); document.querySelector('.cnt').style.opacity=sg(t,st[0].start-.15,.3); hud.style.transform=`translateY(${(1-hin)*-30}px)`;
  const segs=$$('.prog .sg'); segs.forEach((g,j)=>{g.style.transform=`scaleX(${oe(sg(t,.5+j*.08,.5))})`;
    const s=st[j]; $('.fl',g).style.transform=`scaleX(${C.single?cl(t/S[S.length-1].start):cl((t-s.start)/(s.end-s.start))})`;});
  let cur=0; st.forEach((s,j)=>{if(t>=s.start-.05)cur=j});
  const cn=document.getElementById('cn'), s0=st[cur]; cn.textContent=C.fa[cur+1];
  const cp=t<st[0].start-.05?1:oe(sg(t,s0.start-.05,.35)); cn.style.transform=`translateY(${(1-cp)*100}%)`;
  // flash, grain
  const fe=document.getElementById('flash'); fe.style.opacity=flash;
  const gx=Math.floor(rnd(f+1)*128), gy=Math.floor(rnd(f+7)*128); document.getElementById('grain').style.transform=`translate(${gx}px,${gy}px)`;
}
window.__setup=async()=>{await document.fonts.ready; await Promise.all([...document.images].map(i=>i.decode().catch(()=>0))); setup(); return true;};
"""

# ------------------------------------------------------------------ rendering
def _worker(html_path, a, b, frames_dir, fps):
    from playwright.sync_api import sync_playwright
    exe = next((p for p in ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"] if os.path.exists(p)), None)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=exe, args=["--no-sandbox", "--allow-file-access-from-files", "--font-render-hinting=none", "--disable-gpu-vsync"])
        pg = br.new_page(viewport={"width": W, "height": H})
        pg.goto(file_url(html_path), wait_until="load")
        pg.evaluate("window.__setup()")
        for f in range(a, b):
            # R() then wait two animation frames so the screenshot can never show the previous state
            pg.evaluate(f"new Promise(res => {{ R({f / fps:.5f},{f}); requestAnimationFrame(() => requestAnimationFrame(res)); }})")
            pg.screenshot(path=os.path.join(frames_dir, f"f{f:05d}.jpg"), type="jpeg", quality=94)
        br.close()

def snapshot(html_path, t, out_png):
    """render one frame as PNG (used for the cover)."""
    from playwright.sync_api import sync_playwright
    exe = next((p for p in ["/usr/bin/google-chrome", "/usr/bin/chromium"] if os.path.exists(p)), None)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=exe, args=["--no-sandbox", "--allow-file-access-from-files", "--font-render-hinting=none"])
        pg = br.new_page(viewport={"width": W, "height": H})
        pg.goto(file_url(html_path), wait_until="load"); pg.evaluate("window.__setup()")
        pg.evaluate(f"R({t},{int(t * FPS)})"); pg.screenshot(path=out_png)
        br.close()

def make_reel_v2(stories, date_label, build, out_mp4, cover_png, cats, texts, site_url, workers=None, max_stories=7, single=None, multi=None):
    """single = {"hook": "question *highlight*", "kick": "...", "sub": "...", "beats": 16} -> one-story short reel
    (~14s: 3s hook question, ~8s story with summary, 3s outro).
    multi = {"beats": 14, "hook_beats": 6, "withsum": True} -> multi-story reel with longer story scenes + summary line
    (hook texts: texts["kick"], texts["hook"] (*..* = highlight), texts["date"] = line under it)."""
    from reel_audio import music
    t0 = time.time()
    m = multi or {}
    bpm = m.get("bpm", BPM); BEAT = 60 / bpm   # local beat (multi may raise the tempo)
    stories = stories[:1 if single else max_stories]
    n = len(stories)
    beats_story = 10 if n <= 5 else (9 if n == 6 else 8)
    hook_d, story_d, outro_d = 4 * BEAT, beats_story * BEAT, 6 * BEAT
    if single:
        hook_d, story_d, outro_d = single.get("hook_beats", 6) * BEAT, single.get("beats", 16) * BEAT, 6 * BEAT
    elif multi:
        hook_d, story_d = multi.get("hook_beats", 4) * BEAT, multi.get("beats", beats_story) * BEAT
        outro_d = multi.get("outro_beats", 6) * BEAT
    scenes, t = [{"type": "hookS" if single else "hook", "start": 0.0, "end": hook_d}], hook_d
    for i in range(n):
        scenes.append({"type": "story", "i": i, "start": t, "end": t + story_d, "dur": story_d}); t += story_d
    scenes.append({"type": "outro", "start": t, "end": t + outro_d, "dur": outro_d}); total = t + outro_d
    cyc = ["whip", "glitch", "push", "whipR", "glitch", "push"]
    cuts = ["zoom"] + [cyc[i % len(cyc)] for i in range(n - 1)] + ["flash"]
    timeline = {"beat": BEAT, "fps": FPS, "tw": m.get("tw", 0.4), "pre": 0.5, "spd": m.get("spd", 1), "kb": m.get("kb", 1), "scenes": scenes, "cuts": cuts, "fa": [fa(i) for i in range(n + 2)], "single": bool(single)}
    os.makedirs(os.path.join(build, "img"), exist_ok=True)
    prep_images(stories, build)
    grain = make_grain(build)
    texts = dict(texts); texts.setdefault("url", site_url); texts.setdefault("date", date_label)
    html_path = os.path.join(build, "reel_v2.html")
    build_html(stories, cats, texts, timeline, grain, html_path, single, bool(multi and multi.get("withsum")))
    frames = os.path.join(build, "frames"); shutil.rmtree(frames, ignore_errors=True); os.makedirs(frames)
    N = int(round(total * FPS))
    workers = workers or max(1, min(6, (os.cpu_count() or 2) - 1))
    print(f"  reel v2: {n} stories, {total:.1f}s, {N} frames, {workers} workers")
    chunk = math.ceil(N / workers); procs = []
    for w in range(workers):
        a, b = w * chunk, min(N, (w + 1) * chunk)
        if a >= b: continue
        procs.append(subprocess.Popen([sys.executable, os.path.abspath(__file__), "--worker", html_path, str(a), str(b), frames, str(FPS)], cwd=HERE))
    wav = os.path.join(build, "music.wav")
    music(total, [s["end"] for s in scenes[:-1]], scenes[-1]["start"], wav, bpm=bpm)
    for p in procs:
        if p.wait() != 0: raise SystemExit("reel v2: frame worker failed")
    print(f"  frames rendered in {time.time() - t0:.0f}s")
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", os.path.join(frames, "f%05d.jpg"), "-i", wav,
           "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-maxrate", "9M", "-bufsize", "18M", "-profile:v", "high", "-level", "4.1",
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", "-shortest", out_mp4]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: sys.stderr.write(r.stderr[-3000:]); raise SystemExit("reel v2: ffmpeg failed")
    # cover = fully revealed hook, just before the first cut starts (short hooks) or 0.7s before its end
    cover_t = (hook_d - timeline["tw"] * timeline["pre"] - 0.1) if hook_d < 2 else hook_d - 0.7
    if not (single or multi): cover_t = 1.75
    subprocess.run([sys.executable, os.path.abspath(__file__), "--snap", html_path, f"{cover_t:.2f}", cover_png], cwd=HERE, check=True)
    print(f"  reel v2 done in {time.time() - t0:.0f}s ({os.path.getsize(out_mp4) / 1e6:.1f} MB)")
    return total

# ================================================================== text-card mode
# Kinetic-typography reel built only from text cards (no story images needed), in the site palette
# (#0b0c0f / #ff5a4e).  Spec = JSON: {"bpm":128,"cards":[{"beats":3,"cut":"zoom","wm":"Qoder","els":[...]}, ...],
#   "outro":{"beats":4,"tag":"...","handle":"@nabz_farda"}}
# element types: chip (accent pill), small, big (words), accent (words, accent colour), huge (Latin logo-word),
#   name (Latin model name, auto-fit), sub, checks (list "items"), strike (crossed-out word), btn, line.
#   Words wrapped in *..* inside big/accent/sub/small are highlighted in the accent colour.
# CLI: python3 reel_v2.py --cards spec.json OUT_DIR   -> reel.mp4, reel_cover.png, cover.png
CARD_CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;overflow:hidden;background:#0b0c0f}
body{font-family:Vazirmatn,sans-serif;direction:rtl;color:#ececee;-webkit-font-smoothing:antialiased}
#stage{position:relative;width:1080px;height:1920px;overflow:hidden;background:#0b0c0f;--acc:#ff5a4e}
.bgrid{position:absolute;inset:-120px;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);
  background-size:96px 96px;-webkit-mask-image:radial-gradient(closest-side at 50% 45%,#000 25%,transparent 100%)}
#glow{position:absolute;left:50%;top:860px;width:1300px;height:1000px;margin:-500px 0 0 -650px;border-radius:50%;
  background:radial-gradient(closest-side,rgba(255,90,78,.20),rgba(255,90,78,.06) 55%,rgba(255,90,78,0))}
.sc{position:absolute;inset:0;display:none;transform-origin:50% 45%}
.wm{position:absolute;top:640px;left:0;white-space:nowrap;direction:ltr;font-size:430px;line-height:1;font-weight:900;color:transparent;
  -webkit-text-stroke:2px rgba(255,255,255,.06);letter-spacing:-8px}
.stack{position:absolute;left:80px;right:80px;top:330px;bottom:470px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:30px}
.w{display:inline-block;overflow:hidden;vertical-align:top;padding:.14em .05em .3em;margin:-.14em -.05em -.3em}
.wi{display:inline-block}
.hl .wi,.e-accent .wi{color:var(--acc)}
.e-big,.e-accent,.e-sub,.e-small{text-wrap:balance}
.e-chip{display:inline-flex;align-items:center;gap:14px;font-size:38px;font-weight:900;color:#fff;background:var(--acc);padding:10px 34px 15px;border-radius:99px;
  box-shadow:0 14px 40px -14px rgba(255,90,78,.8)}
.e-chip i{width:12px;height:12px;border-radius:50%;background:#fff}
.e-small{font-size:46px;font-weight:700;color:#a1a2a9;line-height:1.5}
.e-big{font-size:112px;font-weight:900;line-height:1.32;letter-spacing:-1px}
.e-accent{font-size:124px;font-weight:900;line-height:1.3;letter-spacing:-1px}
.e-huge{direction:ltr;font-size:250px;font-weight:900;line-height:1.05;letter-spacing:-6px;color:#fff}
.e-name{direction:ltr;font-size:120px;font-weight:900;line-height:1.15;letter-spacing:-2px;color:#fff;white-space:nowrap}
.e-sub{font-size:44px;font-weight:600;color:#c9cad0;line-height:1.6;max-width:880px}
.e-line{width:170px;height:8px;border-radius:4px;background:var(--acc)}
.e-checks{display:flex;flex-direction:column;gap:26px;align-items:stretch;margin-top:6px}
.ck{display:flex;align-items:center;gap:24px;font-size:50px;font-weight:800;color:#ececee;text-align:right;
  background:#131418;border:1.5px solid rgba(255,255,255,.08);border-radius:28px;padding:22px 34px 28px 40px}
.ck b{flex:none;width:58px;height:58px;border-radius:50%;background:var(--acc);display:grid;place-items:center}
.ck b svg{width:34px;height:34px;fill:none;stroke:#fff;stroke-width:3.4;stroke-linecap:round;stroke-linejoin:round}
.e-strike{position:relative;font-size:118px;font-weight:900;color:#ececee;line-height:1.3}
.e-strike .bar{position:absolute;left:-14px;right:-14px;top:56%;height:12px;border-radius:6px;background:var(--acc);transform-origin:100% 50%}
.e-btn{display:inline-flex;align-items:center;gap:16px;font-size:52px;font-weight:900;color:#fff;background:var(--acc);padding:20px 58px 26px;border-radius:99px;position:relative}
.e-btn .rg{position:absolute;inset:0;border-radius:99px;border:3px solid var(--acc)}
.o-mk{width:190px;height:190px;border-radius:54px;background:#131418;border:1.5px solid rgba(255,255,255,.1);display:grid;place-items:center;box-shadow:0 30px 80px -24px rgba(0,0,0,.9),0 0 0 10px rgba(255,90,78,.07)}
.o-mk svg{width:68%;height:68%}
.o-nm{font-size:150px;font-weight:900;line-height:1.25}
.o-url{direction:ltr;font-size:40px;font-weight:800;color:#ececee;padding:12px 34px 16px;border-radius:22px;background:#131418;border:1.5px solid rgba(255,90,78,.45)}
#hud{position:absolute;left:70px;right:70px;top:262px;height:100px;z-index:50}
#hud .hb{position:absolute;right:0;top:0;display:flex;align-items:center;gap:14px}
#hud .mk{width:56px;height:56px;border-radius:16px;background:#131418;border:1px solid rgba(255,255,255,.12);display:grid;place-items:center}
#hud .mk svg{width:70%;height:70%}
#hud b{font-size:32px;font-weight:900;color:#fff}
#hud .hdl{position:absolute;left:0;top:10px;direction:ltr;font-size:28px;font-weight:700;color:#6f7078}
#prog{position:absolute;left:0;right:0;top:80px;height:6px;border-radius:3px;background:rgba(255,255,255,.12);overflow:hidden}
#prog i{position:absolute;inset:0;background:var(--acc);transform-origin:100% 50%;transform:scaleX(0)}
#flash{position:absolute;inset:0;background:#fff3f1;opacity:0;z-index:80}
#grain{position:absolute;inset:-128px;opacity:.07;mix-blend-mode:overlay;z-index:90}
#vig{position:absolute;inset:0;z-index:85;background:radial-gradient(140% 90% at 50% 45%,transparent 55%,rgba(0,0,0,.5))}
"""
CHECK_SVG = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
def card_logo(i):
    return (f'<svg viewBox="0 0 48 48"><path d="{LOGO_PATH}" fill="none" stroke="#ff5a4e" stroke-width="4.2" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>')

def _el_html(e):
    t = e["t"]; tx = e.get("text", "")
    if t == "chip": return f'<div class="el e-chip"><i></i>{esc(tx)}</div>'
    if t in ("big", "accent", "sub", "small"): return f'<div class="el e-{t}" data-words="1">{hook_words_html(tx)}</div>'
    if t in ("huge", "name"): return f'<div class="el e-{t}" data-fit="1">{esc(tx)}</div>'
    if t == "line": return '<div class="el e-line"></div>'
    if t == "checks": return ('<div class="el e-checks">' + "".join(f'<div class="ck"><b>{CHECK_SVG}</b><span>{esc(x)}</span></div>' for x in e["items"]) + '</div>')
    if t == "strike": return f'<div class="el e-strike"><span class="tx">{esc(tx)}</span><i class="bar"></i></div>'
    if t == "btn": return f'<div class="el e-btn"><i class="rg"></i>{esc(tx)}</div>'
    raise ValueError(t)

CARD_JS = r"""
const C=window.CFG;const cl=x=>Math.max(0,Math.min(1,x)),lerp=(a,b,p)=>a+(b-a)*p,sg=(t,a,d)=>cl((t-a)/d);
const oc=x=>1-Math.pow(1-x,3),ic=x=>x*x*x,oq=x=>1-Math.pow(1-x,5),oe=x=>x>=1?1:1-Math.pow(2,-10*x),io=x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2,
  ob=x=>{const c1=1.9,c3=c1+1;return 1+c3*Math.pow(x-1,3)+c1*Math.pow(x-1,2)};
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const S=C.scenes.map((sc,k)=>({...sc,el:document.getElementById('c'+k),k}));
const B=C.beat; function pulse(t){const p=((t%B)+B)%B;return Math.exp(-p*9)}
function rnd(i){const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x)}
window.WARN=[];
function setup(){
  for(const s of S){ s.el.style.display='block';
    for(const e of $$('[data-fit]',s.el)){let fs=parseFloat(getComputedStyle(e).fontSize);while(e.scrollWidth>900&&fs>60){fs-=4;e.style.fontSize=fs+'px'}}
    for(const e of $$('[data-words]',s.el)){let fs=parseFloat(getComputedStyle(e).fontSize);const lh=parseFloat(getComputedStyle(e).lineHeight)/fs;
      while(e.getBoundingClientRect().height>fs*lh*(+(e.dataset.max||3))+4&&fs>34){fs-=3;e.style.fontSize=fs+'px'}}
    const st=$('.stack',s.el); if(st.scrollHeight>st.clientHeight+2) WARN.push('stack overflow in card '+s.k);
    s.els=$$('.stack > .el',s.el).map((el,i)=>({el,i,ws:$$('.wi',el),cks:$$('.ck',el),bar:$('.bar',el),rg:$('.rg',el)}));
    s.wm=$('.wm',s.el); s.el.style.display='none'; }
}
function animScene(s,lt,t){
  const D=s.end-s.start, u=cl(lt/D), st=$('.stack',s.el);
  st.style.transform=`scale(${lerp(1,1.035,u)}) translateY(${lerp(10,-14,u)}px)`;
  if(s.wm) s.wm.style.transform=`translateX(${lerp(s.k%2?-260:-40,s.k%2?-40:-260,u)}px)`;
  let d=0;
  for(const o of s.els){ const cls=o.el.className, d0=d;
    if(cls.includes('e-chip')||cls.includes('e-btn')){const p=sg(lt,d0,.38);o.el.style.transform=`scale(${ob(p)*(1+(lt>d0+.5?.035*pulse(t):0))})`;o.el.style.opacity=cl(p*4);d+=.1;
      if(o.rg){const ph=((t%B)+B)%B/B;o.rg.style.transform=`scale(${1+ph*.18},${1+ph*.5})`;o.rg.style.opacity=lt>d0+.4?(1-ph)*.7:0;}}
    else if(o.cks.length){o.cks.forEach((c,i)=>{const p=oc(sg(lt,d0+i*.16,.4));c.style.transform=`translateX(${(1-p)*-70}px)`;c.style.opacity=p;
      const b=$('b',c),q=sg(lt,d0+i*.16+.12,.35);b.style.transform=`scale(${ob(q)})`;});d+=.16*o.cks.length;}
    else if(o.ws.length){o.ws.forEach((w,i)=>{const p=oq(sg(lt,d0+i*.045,.36));w.style.transform=`translateY(${(1-p)*115}%) rotate(${(1-p)*3}deg)`;w.style.visibility=p<=0?'hidden':'visible'});
      d+=.08+o.ws.length*.045;}
    else if(cls.includes('e-huge')||cls.includes('e-name')){const p=oe(sg(lt,d0,.5));o.el.style.transform=`scale(${lerp(1.3,1,p)*lerp(1,1.03,u)})`;o.el.style.filter=`blur(${(1-p)*14}px)`;o.el.style.opacity=cl(p*2.5);d+=.22;}
    else if(cls.includes('e-line')){const p=oe(sg(lt,d0,.45));o.el.style.transform=`scaleX(${p})`;d+=.06;}
    else if(cls.includes('e-strike')){const p=oc(sg(lt,d0,.3));o.el.style.opacity=p;o.el.style.transform=`translateY(${(1-p)*30}px)`;
      const q=oe(sg(lt,d0+.32,.35));o.bar.style.transform=`scaleX(${q}) rotate(-4deg)`;$('.tx',o.el).style.opacity=lerp(1,.45,q);d+=.5;}
    else {const p=oc(sg(lt,d0,.4));o.el.style.opacity=p;o.el.style.transform=`translateY(${(1-p)*26}px)`;d+=.1;}
  }
  if(s.out){const e=oc(sg(lt,D-.4,.38)); st.style.opacity=1-e;}
}
function setT(s,o){s.el.style.transform=`translate(${o.tx||0}px,${o.ty||0}px) scale(${o.s||1})`;s.el.style.opacity=o.op==null?1:o.op;
  s.el.style.filter=o.bl?`blur(${o.bl}px)`:'none';}
function trans(type,p){
  switch(type){
    case 'zoom':{const a=ic(cl(p/.5)),b=oe(cl((p-.45)/.55));return [{s:1+.6*a,op:1-a,bl:10*a},{s:lerp(.84,1,b),op:cl((p-.42)/.14),bl:(1-b)*8},.1*Math.exp(-Math.pow((p-.5)/.1,2)),p>.45];}
    case 'push':{const x=io(p),bl=26*Math.sin(Math.PI*p);return [{ty:-1920*x,bl},{ty:1920*(1-x),bl},0,true];}
    case 'whip':{const x=io(p),bl=30*Math.sin(Math.PI*p);return [{tx:1080*x,bl},{tx:-1080*(1-x),bl},0,true];}
    case 'whipL':{const x=io(p),bl=30*Math.sin(Math.PI*p);return [{tx:-1080*x,bl},{tx:1080*(1-x),bl},0,true];}
    case 'flash':{const a=cl(p/.5),b=oe(cl((p-.5)/.5));return [{s:1+.08*ic(a)},{s:lerp(1.12,1,b)},.5*Math.exp(-Math.pow((p-.5)/.1,2)),p>=.5];}
  }
}
function R(t,f){
  const TW=C.tw;let flash=0;
  for(const s of S){const vis=t>=s.start-TW/2&&t<s.end+TW/2;s.el.style.display=vis?'block':'none';if(vis){setT(s,{});s.el.style.zIndex=1;}s.vis=vis;}
  for(let k=0;k<S.length-1;k++){const a=S[k].end-TW/2;if(t>=a&&t<a+TW){const [o,i,fl,top]=trans(S[k+1].cut||'zoom',(t-a)/TW);setT(S[k],o);setT(S[k+1],i);flash=Math.max(flash,fl);
    S[k].el.style.zIndex=top?1:2;S[k+1].el.style.zIndex=top?2:1;}}
  for(const s of S) if(s.vis) animScene(s,Math.max(0,t-s.start),t);
  const hud=$('#hud'); const hi=oc(sg(t,.1,.4)), ho=sg(t,S[S.length-1].start-.1,.3); hud.style.opacity=hi*(1-ho);
  $('#prog i').style.transform=`scaleX(${cl(t/S[S.length-1].start)})`;
  $('#glow').style.transform=`translate(${Math.sin(t*1.1)*90}px,${Math.cos(t*.8)*70}px) scale(${1+.06*pulse(t)})`;
  $('#flash').style.opacity=flash;
  $('#grain').style.transform=`translate(${Math.floor(rnd(f+1)*128)}px,${Math.floor(rnd(f+7)*128)}px)`;
}
window.__setup=async()=>{await document.fonts.ready;setup();return WARN;};
"""

def make_cards_reel(spec, out_dir, build, workers=None):
    from reel_audio import music
    t0 = time.time()
    bpm = spec.get("bpm", 128); beat = 60 / bpm
    cards = list(spec["cards"]); o = spec.get("outro", {})
    scenes, t = [], 0.0
    for c in cards:
        d = c["beats"] * beat; scenes.append({"start": t, "end": t + d, "cut": c.get("cut", "zoom")}); t += d
    od = o.get("beats", 4) * beat
    scenes.append({"start": t, "end": t + od, "cut": o.get("cut", "flash"), "out": True}); total = t + od
    os.makedirs(os.path.join(build, "img"), exist_ok=True)
    grain = make_grain(build)
    faces = "".join(
        f"@font-face{{font-family:Vazirmatn;src:url('{file_url(os.path.join(FONT_DIR, f'Vazirmatn-{nm}.ttf'))}') format('truetype');font-weight:{wg};font-display:block}}"
        for nm, wg in [("Regular", 400), ("Medium", 500), ("Bold", 700), ("ExtraBold", 800), ("Black", 900)])
    sc = []
    for k, c in enumerate(cards):
        wm = f'<div class="wm">{esc(c["wm"])}</div>' if c.get("wm") else ""
        sc.append(f'<div class="sc" id="c{k}">{wm}<div class="stack">{"".join(_el_html(e) for e in c["els"])}</div></div>')
    k = len(cards)
    tag = esc(o.get("tag", "هر روز داغ‌ترین خبرهای هوش مصنوعی، تکنولوژی و گیم")).replace("\n", "<br>")
    sc.append(f"""<div class="sc" id="c{k}"><div class="stack" style="gap:34px">
  <div class="el o-mk">{card_logo(k)}</div>
  <div class="el e-big o-nm" data-words="1" data-max="1">{hook_words_html("نبض فردا")}</div>
  <div class="el e-sub" style="max-width:820px;font-size:38px;color:#a1a2a9">{tag}</div>
  <div class="el e-btn"><i class="rg"></i>{esc(o.get("btn", "دنبال کن"))} <span style="direction:ltr;font-weight:800;opacity:.9">{esc(o.get("handle", "@nabz_farda"))}</span></div>
  <div class="el o-url">{esc(o.get("url", "nabz-farda.vercel.app"))}</div></div></div>""")
    hud = (f'<div id="hud"><div class="hb"><span class="mk">{card_logo(99)}</span><b>نبض فردا</b></div>'
           f'<div class="hdl">@nabz_farda</div><div id="prog"><i></i></div></div>')
    timeline = {"beat": beat, "tw": spec.get("tw", 0.3), "scenes": scenes, "total": total}
    page = (f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{faces}{CARD_CSS}</style></head><body>'
            f'<div id="stage"><div class="bgrid"></div><div id="glow"></div>{"".join(sc)}{hud}<div id="vig"></div><div id="flash"></div>'
            f'<div id="grain" style="background-image:url(\'{file_url(grain)}\')"></div></div>'
            f'<script>window.CFG={json.dumps(timeline)};</script><script>{CARD_JS}</script></body></html>')
    html_path = os.path.join(build, "cards.html"); open(html_path, "w", encoding="utf-8").write(page)
    frames = os.path.join(build, "frames"); shutil.rmtree(frames, ignore_errors=True); os.makedirs(frames)
    N = int(round(total * FPS)); workers = workers or max(1, min(6, (os.cpu_count() or 2) - 1))
    print(f"  cards reel: {len(cards)} cards + outro, {total:.2f}s @ {bpm} BPM, {N} frames, {workers} workers")
    chunk = math.ceil(N / workers); procs = []
    for w in range(workers):
        a, b = w * chunk, min(N, (w + 1) * chunk)
        if a < b: procs.append(subprocess.Popen([sys.executable, os.path.abspath(__file__), "--worker", html_path, str(a), str(b), frames, str(FPS)], cwd=HERE))
    wav = os.path.join(build, "music.wav")
    music(total, [s["end"] for s in scenes[:-1]], scenes[-1]["start"], wav, bpm=bpm)
    for p in procs:
        if p.wait() != 0: raise SystemExit("cards reel: frame worker failed")
    out_mp4 = os.path.join(out_dir, "reel.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", os.path.join(frames, "f%05d.jpg"), "-i", wav,
           "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-maxrate", "9M", "-bufsize", "18M", "-profile:v", "high", "-level", "4.1",
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", "-shortest", out_mp4]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: sys.stderr.write(r.stderr[-3000:]); raise SystemExit("cards reel: ffmpeg failed")
    cover_t = spec.get("cover_t", scenes[0]["end"] - timeline["tw"] / 2 - 0.08)   # fully revealed hook, before the first cut
    cover = os.path.join(out_dir, "reel_cover.png")
    subprocess.run([sys.executable, os.path.abspath(__file__), "--snap", html_path, f"{cover_t:.2f}", cover], cwd=HERE, check=True)
    shutil.copyfile(cover, os.path.join(out_dir, "cover.png"))
    print(f"  cards reel done in {time.time() - t0:.0f}s ({os.path.getsize(out_mp4) / 1e6:.1f} MB)")
    return total, scenes

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--worker":
    _worker(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], int(sys.argv[6]))
elif __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--snap":
    snapshot(sys.argv[2], float(sys.argv[3]), sys.argv[4])
elif __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--cards":
    import hashlib
    spec = json.load(open(sys.argv[2], encoding="utf-8")); out = sys.argv[3]; os.makedirs(out, exist_ok=True)
    build = os.path.join(HERE, ".cache", "build", "cards-" + hashlib.sha1(os.path.abspath(out).encode()).hexdigest()[:8])
    shutil.rmtree(build, ignore_errors=True); os.makedirs(build)
    total, scenes = make_cards_reel(spec, out, build)
    print(json.dumps({"total": round(total, 3), "scenes": [[round(x["start"], 3), round(x["end"], 3)] for x in scenes]}))
