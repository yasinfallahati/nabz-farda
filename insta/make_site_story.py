#!/usr/bin/env python3
"""make_site_story.py — 12s loopable Instagram STORY (1080x1920) promoting nabz-farda.vercel.app.
Captures the live homepage at 390px (mobile, full page), scrolls it inside a flat phone mockup,
renders frames with headless Chrome (reel_v2 worker) and muxes the generated 120 BPM track + SFX.

Usage: python3 make_site_story.py [--out /workspace/insta/site_promo] [--no-capture]
Outputs: story.mp4 (H.264+AAC, 30fps), story.png (static version)."""
import argparse, json, math, os, shutil, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from reel_v2 import FONT_DIR, file_url, words_html, esc, make_grain
from reel_audio import music

URL = "https://nabz-farda.vercel.app"
FPS, BEAT, TOTAL = 30, 0.5, 12.0
CHROME = next((p for p in ["/usr/bin/google-chrome", "/usr/bin/chromium"] if os.path.exists(p)), None)

def capture(build):
    from playwright.sync_api import sync_playwright
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True,
                            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
        pg = ctx.new_page(); pg.goto(URL, wait_until="networkidle", timeout=90000)
        pg.evaluate("document.querySelectorAll('img').forEach(i=>{i.loading='eager';i.decoding='sync'})")
        h = pg.evaluate("document.body.scrollHeight")
        for y in range(0, h, 400): pg.evaluate(f"window.scrollTo(0,{y})"); pg.wait_for_timeout(250)
        pg.evaluate("window.scrollTo(0,0)")
        try:
            pg.wait_for_function("[...document.images].filter(i=>i.getBoundingClientRect().top<4000).every(i=>i.complete&&i.naturalWidth>0)", timeout=20000)
        except Exception as e:
            print("  ! some images did not load:", pg.evaluate("[...document.images].filter(i=>!(i.complete&&i.naturalWidth>0)).length"))
        pg.wait_for_timeout(1200)
        hh = pg.evaluate("Math.round((document.querySelector('header')||{getBoundingClientRect:()=>({height:0})}).getBoundingClientRect().height)")
        pg.screenshot(path=os.path.join(build, "site_full.png"), full_page=True)
        b.close()
    im = Image.open(os.path.join(build, "site_full.png")).convert("RGB")
    hp = hh * 3
    im.crop((0, 0, im.width, hp)).save(os.path.join(build, "header.png"))
    im.crop((0, hp, im.width, min(im.height, hp + 9900))).save(os.path.join(build, "content.jpg"), quality=90)
    return hh

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;overflow:hidden;background:#0b0c0f}
body{font-family:Vazirmatn,sans-serif;direction:rtl;color:#f2f2f3;-webkit-font-smoothing:antialiased}
#stage{position:relative;width:1080px;height:1920px;overflow:hidden;background:#0b0c0f}
.grid{position:absolute;inset:-96px;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);
  background-size:96px 96px;-webkit-mask-image:radial-gradient(closest-side at 50% 50%,#000 25%,transparent 100%)}
.glow{position:absolute;left:140px;top:560px;width:800px;height:800px;border-radius:50%;background:radial-gradient(closest-side,rgba(255,90,78,.13),rgba(255,90,78,0))}
.w{display:inline-block;overflow:hidden;vertical-align:top;padding:.16em .06em .34em;margin:-.16em -.06em -.34em}
.wi{display:inline-block}
.layer{position:absolute;inset:0}
/* hook */
.hk{position:absolute;left:70px;right:70px;text-align:center;font-weight:900;color:#fff;letter-spacing:-1px}
.hk.l{font-size:112px;line-height:1.25}
.hk .acc{color:#ff5a4e}
.chips{position:absolute;left:0;right:0;top:1150px;display:flex;justify-content:center;align-items:center;gap:22px}
.chips span{font-size:52px;font-weight:800;color:#d9dade}
.chips i{width:12px;height:12px;border-radius:50%;background:#ff5a4e;display:inline-block}
.bar{position:absolute;height:6px;border-radius:3px;background:#ff5a4e;transform-origin:100% 50%}
.mark{display:inline-grid;place-items:center;width:64px;height:64px;border-radius:18px;background:#16181d;border:1.5px solid rgba(255,255,255,.1)}
.mark svg{width:70%;height:70%}
/* phone */
.top{position:absolute;top:276px;left:0;right:0;text-align:center}
.pill{display:inline-flex;align-items:center;gap:14px;direction:ltr;font-size:32px;font-weight:800;color:#e9e9ec;padding:12px 30px 15px;border-radius:99px;background:#15171c;border:1.5px solid rgba(255,255,255,.1)}
.pill i{width:12px;height:12px;border-radius:50%;background:#ff5a4e;box-shadow:0 0 0 6px rgba(255,90,78,.18)}
#phone{position:absolute;left:268px;top:392px;width:544px;height:1150px;border-radius:70px;background:#1b1d22;border:1.5px solid rgba(255,255,255,.14);padding:12px;
  box-shadow:0 60px 120px -30px rgba(0,0,0,.9)}
.scr{position:relative;width:520px;height:1126px;border-radius:58px;overflow:hidden;background:#0b0c0f}
.sb{position:absolute;left:0;right:0;top:0;height:60px;background:#0b0c0f;z-index:3;direction:ltr;display:flex;justify-content:space-between;align-items:center;padding:6px 44px 0}
.sb b{font-family:Vazirmatn;font-size:22px;font-weight:800;color:#fff}
.sb .ic{display:flex;gap:8px;align-items:center}
.sig{display:flex;gap:3px;align-items:flex-end}.sig u{display:block;width:5px;background:#fff;border-radius:1px}
.bat{width:34px;height:16px;border:2px solid rgba(255,255,255,.8);border-radius:5px;padding:2px}.bat u{display:block;height:100%;width:75%;background:#fff;border-radius:2px}
.isl{position:absolute;left:50%;top:14px;width:124px;height:36px;margin-left:-62px;border-radius:20px;background:#000;z-index:4}
.hdr{position:absolute;left:0;top:60px;width:520px;z-index:2}
.cv{position:absolute;left:0;right:0;top:var(--ct,196px);bottom:0;overflow:hidden}
.cv img{position:absolute;left:0;width:520px}
.home{position:absolute;left:50%;bottom:12px;width:160px;height:6px;margin-left:-80px;border-radius:3px;background:rgba(255,255,255,.55);z-index:4}
.co{position:absolute;display:flex;align-items:center;gap:18px;padding:20px 30px 22px 22px;border-radius:26px;background:#15171c;border:1.5px solid rgba(255,255,255,.1);
  box-shadow:0 30px 60px -20px rgba(0,0,0,.85);white-space:nowrap}
.co b{font-size:36px;font-weight:800;color:#fff}
.co .ico{width:58px;height:58px;border-radius:16px;background:rgba(255,90,78,.12);display:grid;place-items:center}
.co svg{width:32px;height:32px;fill:none;stroke:#ff5a4e;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
/* end */
.wm{position:absolute;top:520px;left:0;right:0;display:flex;justify-content:center;align-items:center;gap:20px}
.wm b{font-size:64px;font-weight:900}
.url1{position:absolute;top:700px;left:0;right:0;text-align:center;direction:ltr;font-size:168px;line-height:1.15;font-weight:900;letter-spacing:-4px;color:#fff}
.url2{position:absolute;top:910px;left:0;right:0;text-align:center;direction:ltr;font-size:66px;font-weight:700;color:#8b8d96;letter-spacing:-.5px}
.ch{display:inline-block;overflow:hidden;vertical-align:top;padding:.05em 0 .12em;margin:-.05em 0 -.12em}.ch span{display:inline-block}
.cta{position:absolute;top:1150px;left:0;right:0;text-align:center}
.cta span{display:inline-flex;align-items:center;gap:16px;font-size:50px;font-weight:900;color:#0b0c0f;background:#ff5a4e;padding:20px 54px 26px;border-radius:99px}
.cta svg{width:44px;height:44px;fill:none;stroke:#0b0c0f;stroke-width:2.8;stroke-linecap:round;stroke-linejoin:round}
.sub{position:absolute;top:1300px;left:0;right:0;text-align:center;font-size:34px;font-weight:700;color:#8b8d96}
#grain{position:absolute;inset:-128px;opacity:.06;mix-blend-mode:overlay;pointer-events:none;z-index:90}
#fb{position:absolute;inset:0;background:#0b0c0f;opacity:0;z-index:80;pointer-events:none}
"""
ICONS = {
    "story": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke-dasharray="4 2.2"/><circle cx="12" cy="12" r="4.5"/></svg>',
    "moon": '<svg viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg>',
    "doc": '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 15h7M9 7h4"/></svg>',
}
LOGO = ('<svg viewBox="0 0 48 48"><path d="M3 26h9l4-10 7 20 6-26 5 16h11" fill="none" stroke="#ff5a4e" stroke-width="4" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')
UP = '<svg viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></svg>'

def chars(s, cls="ch"):
    return "".join(f'<span class="{cls}"><span>{esc(c)}</span></span>' for c in s)

def build_html(build, grain, content_h, ct):
    faces = "".join(f"@font-face{{font-family:Vazirmatn;src:url('{file_url(os.path.join(FONT_DIR, f'Vazirmatn-{n}.ttf'))}');font-weight:{w}}}"
                    for n, w in [("Regular", 400), ("Medium", 500), ("Bold", 700), ("ExtraBold", 800), ("Black", 900)])
    co = [("story", "استوری خبرهای فوری", "left:34px;top:690px", "l"),
          ("moon", "هر شب آپدیت", "right:34px;top:1010px", "r"),
          ("doc", "خلاصه و فارسی", "left:34px;top:1330px", "l")]
    co_html = "".join(f'<div class="co" id="co{i}" data-side="{sd}" style="{pos}"><span class="ico">{ICONS[ic]}</span><b>{tx}</b></div>'
                      for i, (ic, tx, pos, sd) in enumerate(co))
    html = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{faces}{CSS}</style></head><body>
<div id="stage"><div class="grid" id="grid"></div><div class="glow" id="glow"></div>
<div class="layer" id="hook">
  <div class="hk l" style="top:560px" id="h1">{words_html("همه‌ی خبرهای")}</div>
  <div class="hk l" style="top:700px" id="h2">{words_html("گیم، تکنولوژی")}</div>
  <div class="hk l" style="top:840px" id="h3">{words_html("و هوش مصنوعی")}</div>
  <div class="bar" id="hbar" style="top:1060px;right:390px;width:300px"></div>
  <div class="chips" id="chips"><span>یه جا</span><i></i><span>فارسی</span><i></i><span>هر روز</span></div>
</div>
<div class="layer" id="ph">
  <div class="top" id="toppill"><span class="pill"><i></i>nabz-farda.vercel.app</span></div>
  <div id="phone"><div class="scr">
    <div class="sb"><b>9:41</b><span class="ic"><span class="sig"><u style="height:6px"></u><u style="height:9px"></u><u style="height:12px"></u><u style="height:15px"></u></span><span class="bat"><u></u></span></span></div>
    <div class="isl"></div>
    <img class="hdr" src="{file_url(os.path.join(build, 'header.png'))}">
    <div class="cv" id="cv" style="--ct:{ct}px"><img id="cimg" src="{file_url(os.path.join(build, 'content.jpg'))}"></div>
    <div class="home"></div>
  </div></div>
  {co_html}
</div>
<div class="layer" id="end">
  <div class="wm" id="wm"><span class="mark">{LOGO}</span><b>نبض فردا</b></div>
  <div class="url1" id="u1">{chars("nabz-farda")}</div>
  <div class="url2" id="u2">{chars(".vercel.app")}</div>
  <div class="bar" id="ebar" style="top:1030px;left:440px;width:200px;transform-origin:50% 50%"></div>
  <div class="cta" id="cta"><span>ورود به سایت<i id="arr" style="display:inline-flex">{UP}</i></span></div>
  <div class="sub" id="sub">یا از لینک بیو</div>
</div>
<div id="fb"></div><div id="grain" style="background-image:url('{file_url(grain)}')"></div></div>
<script>window.CFG={json.dumps({"beat": BEAT, "total": TOTAL, "ch": content_h, "ct": ct})};</script><script>{JS}</script></body></html>"""
    p = os.path.join(build, "story.html"); open(p, "w", encoding="utf-8").write(html); return p

JS = r"""
const C=window.CFG,B=C.beat;
const cl=x=>Math.max(0,Math.min(1,x)),lerp=(a,b,p)=>a+(b-a)*p,sg=(t,a,d)=>cl((t-a)/d);
const oc=x=>1-Math.pow(1-x,3),ic=x=>x*x*x,oq=x=>1-Math.pow(1-x,5),oe=x=>x>=1?1:1-Math.pow(2,-10*x),
 io=x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2,ob=x=>{const c1=1.7,c3=c1+1;return 1+c3*Math.pow(x-1,3)+c1*Math.pow(x-1,2)};
const $=id=>document.getElementById(id),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const bp=t=>{const p=((t%B)+B)%B;return Math.exp(-p*9)};
function rnd(i){const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x)}
function words(ws,t,st,stag,d,dist){ws.forEach((w,i)=>{const p=oq(sg(t,st+i*stag,d));w.style.transform=`translateY(${(1-p)*dist}%)`;w.style.visibility=p<=0?'hidden':'visible'})}
// scroll keyframes (content px): [t0,t1,y0,y1]
const SK=[[3.35,4.25,0,620],[4.85,5.85,620,1500],[6.35,7.45,1500,2560]];
function scrollAt(t){let y=0;for(const [a,b,y0,y1] of SK){if(t>=a)y=lerp(y0,y1,io(sg(t,a,b-a)))}return Math.min(y,C.ch-(1126-C.ct))}
function R(t,f){
  // ---------- hook 0-2.0
  const hk=$('hook'), hv=t<2.4; hk.style.display=hv?'block':'none';
  if(hv){
    const ex=ic(sg(t,1.78,.42));
    ['h1','h2','h3'].forEach((id,i)=>{const el=$(id);words($$('.wi',el),t,i*.13,.07,.5,130);
      el.style.transform=`translateY(${-ex*(260-i*40)}px)`;el.style.opacity=1-ex;el.style.filter=ex>0?`blur(${ex*10}px)`:'none'});
    $('hbar').style.transform=`scaleX(${oe(sg(t,.55,.5))})`;$('hbar').style.opacity=1-ex;
    const ch=$('chips'); ch.style.opacity=1-ex; ch.style.transform=`translateY(${-ex*120}px)`;
    $$('#chips span').forEach((s,i)=>{const p=sg(t,1.0+i*.25,.35);s.style.transform=`scale(${ob(p)})`;s.style.opacity=cl(p*4);s.style.display='inline-block'});
    $$('#chips i').forEach((s,i)=>{const p=sg(t,1.12+i*.25,.25);s.style.transform=`scale(${ob(p)})`});
  }
  // ---------- phone 2.0-8.9
  const ph=$('ph'), pv=t>=1.8&&t<8.6; ph.style.display=pv?'block':'none';
  if(pv){
    const en=oq(sg(t,1.95,.75)), ex=sg(t,8.15,.4), exe=ic(ex);
    const P=$('phone');
    P.style.transform=`translateY(${lerp(900,0,en)-exe*260}px) rotate(${lerp(-6,0,en)}deg) scale(${(1-.12*exe)*(1+.012*bp(t)*(t>2.7&&t<8.3?1:0))})`;
    P.style.opacity=1-exe; P.style.filter=ex>0?`blur(${exe*14}px)`:'none';
    $('cimg').style.transform=`translateY(${-scrollAt(t)}px)`;
    const tp=oc(sg(t,2.25,.45)); $('toppill').style.transform=`translateY(${(1-tp)*-40-exe*80}px)`; $('toppill').style.opacity=tp*(1-exe);
    [3.0,4.5,6.0].forEach((ts,i)=>{const el=$('co'+i), l=el.dataset.side==='l', p=sg(t,ts,.5);
      const fl=Math.sin((t-ts)*2.4+i)*6*cl(p*2);
      el.style.transformOrigin=l?'100% 50%':'0% 50%';
      el.style.transform=`translate(${(1-oq(p))*(l?-60:60)}px,${fl-exe*(200+i*60)}px) scale(${ob(p)*(1-.1*exe)})`;
      el.style.opacity=cl(p*4)*(1-exe); el.style.visibility=p>0?'visible':'hidden'});
  }
  // ---------- end 8.4-12
  const en=$('end'), ev=t>=8.45; en.style.display=ev?'block':'none';
  if(ev){
    const lt=t-8.5, fo=oc(sg(t,11.45,.5));
    const w=oq(sg(lt,0,.6)); $('wm').style.transform=`translateY(${(1-w)*50}px) scale(${lerp(.9,1,w)})`; $('wm').style.opacity=w;
    $$('#u1 .ch span').forEach((s,i)=>{const p=oq(sg(lt,.12+i*.035,.5));s.style.transform=`translateY(${(1-p)*110}%)`});
    $$('#u2 .ch span').forEach((s,i)=>{const p=oq(sg(lt,.45+i*.03,.45));s.style.transform=`translateY(${(1-p)*110}%)`});
    $('ebar').style.transform=`scaleX(${oe(sg(lt,.85,.5))})`;
    const c=sg(lt,1.0,.5); $('cta').style.transform=`scale(${ob(c)*(1+.035*(lt>1.5?bp(t):0))})`; $('cta').style.opacity=cl(c*4);
    $('arr').style.transform=`translateY(${-10*(lt>1.5?bp(t):0)}px)`;
    const s=oc(sg(lt,1.35,.4)); $('sub').style.opacity=s; $('sub').style.transform=`translateY(${(1-s)*20}px)`;
    for(const id of ['wm','u1','u2','ebar','cta','sub']){const el=$(id);el.style.opacity=(id==='wm'||id==='cta'||id==='sub'?parseFloat(el.style.opacity):1)*(1-fo)}
    $('u1').style.transform=`scale(${1-.04*fo})`;
  }
  $('glow').style.transform=`translate(${Math.sin(t*.9)*50}px,${Math.cos(t*.7)*60}px) scale(${1+.05*bp(t)})`;
  $('glow').style.opacity=t<2?.6:1;
  $('grid').style.transform=`translateY(${(t*12)%96}px)`;
  const gx=Math.floor(rnd(f+1)*128),gy=Math.floor(rnd(f+7)*128);$('grain').style.transform=`translate(${gx}px,${gy}px)`;
}
window.__setup=async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode().catch(()=>0)));return true};
"""

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=os.path.join(HERE, "site_promo"))
    ap.add_argument("--no-capture", action="store_true"); ap.add_argument("--still-t", type=float, default=7.9)
    a = ap.parse_args()
    out = a.out; build = os.path.join(out, "build"); os.makedirs(os.path.join(build, "img"), exist_ok=True)
    t0 = time.time()
    if not a.no_capture or not os.path.exists(os.path.join(build, "content.jpg")):
        print("capturing", URL); capture(build)
    from PIL import Image
    cw, chh = Image.open(os.path.join(build, "content.jpg")).size
    content_h = chh * 520 / cw
    grain = make_grain(build)
    hw, hh = Image.open(os.path.join(build, "header.png")).size
    ct = round(60 + hh * 520 / hw)
    html = build_html(build, grain, content_h, ct)
    frames = os.path.join(build, "frames"); shutil.rmtree(frames, ignore_errors=True); os.makedirs(frames)
    N = int(round(TOTAL * FPS)); W = 6; ch = math.ceil(N / W); ps = []
    for w in range(W):
        s, e = w * ch, min(N, (w + 1) * ch)
        if s < e: ps.append(subprocess.Popen([sys.executable, os.path.join(HERE, "reel_v2.py"), "--worker", html, str(s), str(e), frames, str(FPS)], cwd=HERE))
    wav = os.path.join(build, "music.wav")
    music(TOTAL, [2.0, 8.5], 11.0, wav, pops=[1.0, 1.25, 1.5, 3.0, 4.5, 6.0, 9.5])
    for p in ps:
        if p.wait(): sys.exit("frame worker failed")
    mp4 = os.path.join(out, "story.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", os.path.join(frames, "f%05d.jpg"), "-i", wav,
                    "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "12M", "-bufsize", "24M", "-profile:v", "high", "-level", "4.1",
                    "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", "-shortest", mp4], check=True)
    subprocess.run([sys.executable, os.path.join(HERE, "reel_v2.py"), "--snap", html, str(a.still_t), os.path.join(out, "story.png")], check=True, cwd=HERE)
    print(f"done in {time.time()-t0:.0f}s -> {mp4} ({os.path.getsize(mp4)/1e6:.1f} MB)")

if __name__ == "__main__":
    main()
