#!/usr/bin/env python3
"""Generate contest one-pager PNGs (landscape + story) for Nabz-e Farda."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "insta" / "assets" / "fonts"
LOGO = ROOT / "public" / "assets" / "logo-512.png"
OUT = Path(__file__).resolve().parent

# Brand: dark + purple / turquoise (contest brief) with heartbeat accent
BG = (8, 10, 16)
BG2 = (14, 16, 24)
TXT = (236, 236, 240)
MUT = (156, 160, 176)
DIM = (100, 104, 120)
PURPLE = (139, 92, 246)       # #8b5cf6
PURPLE_SOFT = (167, 139, 250) # #a78bfa
TEAL = (45, 212, 191)         # #2dd4bf
TEAL_DIM = (20, 184, 166)
CORAL = (255, 90, 78)         # heartbeat echo from site
LINE = (31, 34, 46)
WHITE = (255, 255, 255)


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS / f"Vazirmatn-{weight}.ttf"
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)


def rtl(draw: ImageDraw.ImageDraw, xy, text, **kw):
    kw.setdefault("direction", "rtl")
    kw.setdefault("language", "fa")
    draw.text(xy, text, **kw)


def rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def heartbeat_path(cx, cy, w, h, points=48):
    """Simple ECG-like polyline centered at (cx, cy)."""
    pts = []
    for i in range(points + 1):
        t = i / points
        x = cx - w / 2 + t * w
        # normalized pulse shape
        u = (t - 0.5) * 10
        if -0.35 < u < -0.15:
            y = cy + h * 0.15
        elif -0.15 <= u < -0.05:
            y = cy - h * 0.95
        elif -0.05 <= u < 0.05:
            y = cy + h * 0.75
        elif 0.05 <= u < 0.18:
            y = cy - h * 0.25
        else:
            y = cy + math.sin(u * 1.2) * h * 0.04
        pts.append((x, y))
    return pts


def soft_glow(base: Image.Image, color, center, radius, alpha=70):
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    x, y = center
    for i, a in enumerate((alpha, alpha // 2, alpha // 4)):
        r = radius * (1 - i * 0.28)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*color, a))
    blur = overlay.filter(ImageFilter.GaussianBlur(radius * 0.45))
    return Image.alpha_composite(base.convert("RGBA"), blur)


def draw_logo_mark(draw, x, y, size, color=CORAL, width=3):
    # Approximate SVG path M3 26h9l4-10 7 20 6-26 5 16h11 scaled into box
    s = size / 48
    pts = [
        (3, 26), (12, 26), (16, 16), (23, 36), (29, 10), (34, 26), (45, 26),
    ]
    pts = [(x + px * s, y + py * s) for px, py in pts]
    draw.line(pts, fill=color, width=max(2, int(width * s * 12)), joint="curve")


def pill(draw, text, font_obj, x, y, *, fill, outline, text_fill, pad_x=22, pad_y=12, radius=999):
    bbox = draw.textbbox((0, 0), text, font=font_obj, direction="rtl", language="fa")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w, h = tw + pad_x * 2, th + pad_y * 2
    rounded_rect(draw, (x, y, x + w, y + h), radius, fill=fill, outline=outline, width=2)
    rtl(draw, (x + w / 2, y + h / 2 - 1), text, font=font_obj, fill=text_fill, anchor="mm")
    return w, h


def flow_chip(draw, text, font_obj, cx, cy, *, fill, outline, text_fill, w=150, h=52):
    rounded_rect(draw, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), 16, fill=fill, outline=outline, width=2)
    rtl(draw, (cx, cy - 1), text, font=font_obj, fill=text_fill, anchor="mm")


def render(W: int, H: int, mode: str) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    img = soft_glow(img, PURPLE, (int(W * 0.18), int(H * 0.22)), int(W * 0.28), alpha=55)
    img = soft_glow(img, TEAL, (int(W * 0.82), int(H * 0.78)), int(W * 0.26), alpha=45)
    img = soft_glow(img, PURPLE, (int(W * 0.7), int(H * 0.15)), int(W * 0.18), alpha=30)
    draw = ImageDraw.Draw(img, "RGBA")

    # subtle grid
    for gx in range(0, W, 48):
        draw.line([(gx, 0), (gx, H)], fill=(*LINE, 40), width=1)
    for gy in range(0, H, 48):
        draw.line([(0, gy), (W, gy)], fill=(*LINE, 40), width=1)

    # frame
    m = 36 if mode == "landscape" else 48
    rounded_rect(draw, (m // 2, m // 2, W - m // 2, H - m // 2), 28, outline=(*PURPLE, 60), width=2)

    if mode == "landscape":
        # Header brand
        mark_x, mark_y = 72, 70
        draw_logo_mark(draw, mark_x, mark_y, 56, color=CORAL, width=3)
        # optional logo raster
        if LOGO.exists():
            logo = Image.open(LOGO).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            img.paste(logo, (72, 64), logo)
            draw = ImageDraw.Draw(img, "RGBA")

        f_title = font("ExtraBold", 72)
        f_sub = font("Regular", 28)
        f_body = font("Medium", 26)
        f_pill = font("Bold", 24)
        f_tiny = font("Regular", 22)
        f_flow = font("Bold", 22)
        f_url = font("Bold", 30)

        rtl(draw, (W - 80, 88), "نبض فردا", font=f_title, fill=WHITE, anchor="rm")
        draw.text((80 + 80, 100), "Nabz-e Farda", font=font("Medium", 26), fill=PURPLE_SOFT, anchor="lm")

        tagline = "اتوماسیون اخبار فارسی هوش مصنوعی، تکنولوژی و بازی — کاملاً استاتیک"
        rtl(draw, (W // 2, 190), tagline, font=f_sub, fill=MUT, anchor="mm")

        # heartbeat under tagline
        hb = heartbeat_path(W // 2, 240, W * 0.55, 36)
        draw.line(hb, fill=TEAL + (200,), width=3, joint="curve")
        # small coral spike highlight
        mid = len(hb) // 2
        draw.line(hb[mid - 4: mid + 5], fill=CORAL + (230,), width=4, joint="curve")

        # Feature pills (2 rows of 3)
        pills = [
            "سایت استاتیک",
            "اتوماسیون شبانه",
            "استوری ۳ساعته",
            "اینستاگرام",
            "تلگرام",
            "داشبورد اتوماسیون",
        ]
        # measure and center
        sizes = []
        for t in pills:
            bb = draw.textbbox((0, 0), t, font=f_pill, direction="rtl", language="fa")
            sizes.append((bb[2] - bb[0] + 44, bb[3] - bb[1] + 24))
        gap = 16
        row1, row2 = pills[:3], pills[3:]
        def place_row(items, y):
            widths = []
            for t in items:
                bb = draw.textbbox((0, 0), t, font=f_pill, direction="rtl", language="fa")
                widths.append(bb[2] - bb[0] + 44)
            total = sum(widths) + gap * (len(items) - 1)
            x = (W - total) / 2
            for t, w in zip(items, widths):
                fill = (22, 18, 36, 220)
                outline = PURPLE + (120,)
                pill(draw, t, f_pill, x, y, fill=fill, outline=outline, text_fill=TXT, pad_x=22, pad_y=12)
                x += w + gap
        place_row(row1, 290)
        place_row(row2, 360)

        # Architecture flow
        rtl(draw, (W // 2, 460), "مسیر داده", font=f_body, fill=DIM, anchor="mm")
        steps = ["RSS", "ترجمه", "سایت", "شبکه‌ها"]
        n = len(steps)
        span = W * 0.72
        start = (W - span) / 2
        ys = 530
        for i, label in enumerate(steps):
            cx = start + (i + 0.5) * (span / n)
            fill = (18, 22, 32, 230)
            outline = (TEAL if i == len(steps) - 1 else PURPLE) + (140,)
            flow_chip(draw, label, f_flow, cx, ys, fill=fill, outline=outline, text_fill=WHITE, w=160, h=56)
            if i < n - 1:
                x1 = cx + 88
                x2 = start + (i + 1.5) * (span / n) - 88
                draw.line([(x1, ys), (x2, ys)], fill=TEAL + (160,), width=3)
                # arrow head (points left in RTL visual flow? keep LTR pipeline left→right)
                draw.polygon([(x2, ys), (x2 - 10, ys - 6), (x2 - 10, ys + 6)], fill=TEAL + (200,))

        # English one-liner
        draw.text(
            (W // 2, 620),
            "Static Persian news automation · Nightly edition + 3h stories · Web / Telegram / Instagram",
            font=font("Regular", 22),
            fill=DIM,
            anchor="mm",
        )

        # URL bar
        url = "nabz-farda.vercel.app"
        ubox_w, ubox_h = 520, 64
        ux, uy = (W - ubox_w) / 2, 680
        rounded_rect(draw, (ux, uy, ux + ubox_w, uy + ubox_h), 20, fill=(16, 20, 30, 240), outline=TEAL + (160,), width=2)
        # teal dot
        draw.ellipse([ux + 22, uy + 24, ux + 38, uy + 40], fill=TEAL)
        draw.text((ux + ubox_w / 2 + 8, uy + ubox_h / 2 - 1), url, font=f_url, fill=WHITE, anchor="mm")

        # footer
        rtl(draw, (W - 80, H - 56), "مسابقه · نسخهٔ یک‌صفحه‌ای", font=f_tiny, fill=DIM, anchor="rm")
        draw.text((80, H - 56), "docs/contest", font=f_tiny, fill=DIM, anchor="lm")

    else:
        # Story / portrait
        if LOGO.exists():
            logo = Image.open(LOGO).convert("RGBA").resize((120, 120), Image.Resampling.LANCZOS)
            img.paste(logo, ((W - 120) // 2, 120), logo)
            draw = ImageDraw.Draw(img, "RGBA")
        else:
            draw_logo_mark(draw, W // 2 - 40, 140, 80, color=CORAL)

        f_title = font("ExtraBold", 92)
        f_sub = font("Regular", 30)
        f_pill = font("Bold", 28)
        f_flow = font("Bold", 26)
        f_url = font("Bold", 36)
        f_tiny = font("Regular", 24)

        rtl(draw, (W // 2, 300), "نبض فردا", font=f_title, fill=WHITE, anchor="mm")
        draw.text((W // 2, 380), "Nabz-e Farda", font=font("Medium", 28), fill=PURPLE_SOFT, anchor="mm")

        lines = [
            "اتوماسیون اخبار فارسی",
            "هوش مصنوعی · تکنولوژی · بازی",
            "کاملاً استاتیک — بدون سرور اپ",
        ]
        y = 460
        for ln in lines:
            rtl(draw, (W // 2, y), ln, font=f_sub, fill=MUT, anchor="mm")
            y += 48

        hb = heartbeat_path(W // 2, 640, W * 0.7, 50)
        draw.line(hb, fill=TEAL + (200,), width=4, joint="curve")

        pills = [
            "سایت استاتیک",
            "اتوماسیون شبانه",
            "استوری ۳ساعته",
            "اینستاگرام",
            "تلگرام",
            "داشبورد اتوماسیون",
        ]
        y = 720
        for t in pills:
            bb = draw.textbbox((0, 0), t, font=f_pill, direction="rtl", language="fa")
            tw = bb[2] - bb[0] + 48
            x = (W - tw) / 2
            pill(draw, t, f_pill, x, y, fill=(22, 18, 36, 220), outline=PURPLE + (130,), text_fill=TXT, pad_x=24, pad_y=14)
            y += 78

        # flow
        draw.text((W // 2, y + 20), "RSS  →  ترجمه  →  سایت  →  شبکه‌ها", font=f_flow, fill=TEAL, anchor="mm", direction="ltr")
        y += 80

        url = "nabz-farda.vercel.app"
        ubox_w, ubox_h = 640, 72
        ux, uy = (W - ubox_w) / 2, min(y + 40, H - 160)
        rounded_rect(draw, (ux, uy, ux + ubox_w, uy + ubox_h), 22, fill=(16, 20, 30, 240), outline=TEAL + (160,), width=2)
        draw.ellipse([ux + 28, uy + 28, ux + 44, uy + 44], fill=TEAL)
        draw.text((W // 2 + 10, uy + ubox_h / 2 - 1), url, font=f_url, fill=WHITE, anchor="mm")

        rtl(draw, (W // 2, H - 70), "یک‌صفحه‌ای مسابقه", font=f_tiny, fill=DIM, anchor="mm")

    return img.convert("RGB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    land = render(1920, 1080, "landscape")
    land_path = OUT / "nabz-farda-onepager.png"
    land.save(land_path, "PNG", optimize=True)
    print(f"wrote {land_path} ({land_path.stat().st_size} bytes)")

    story = render(1080, 1920, "story")
    story_path = OUT / "nabz-farda-onepager-story.png"
    story.save(story_path, "PNG", optimize=True)
    print(f"wrote {story_path} ({story_path.stat().st_size} bytes)")

    # PDF from landscape
    pdf_path = OUT / "nabz-farda-onepager.pdf"
    land_rgb = land.convert("RGB")
    land_rgb.save(pdf_path, "PDF", resolution=150.0)
    print(f"wrote {pdf_path} ({pdf_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
