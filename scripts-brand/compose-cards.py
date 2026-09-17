#!/usr/bin/env python3
"""Compose the 1920x1080 showcase title/end cards from Agnes-generated
backgrounds: center-crop the 1024² art to 16:9, upscale, darken for contrast,
overlay crisp brand text (AI renders CJK text unreliably, so PIL draws it)."""
from PIL import Image, ImageDraw, ImageFilter, ImageFont

VID = "/workspace/FinHub/screenshots/video"
W, H = 1920, 1080
AMBER = (245, 158, 11)
FONT = "/usr/share/fonts/truetype/noto/NotoSerifCJK-Bold.ttc"

def compose(bg_path, out_path, lines, sub):
    img = Image.open(bg_path).convert("RGB")
    # center-crop square -> 16:9, then upscale to 1920x1080
    cw = img.width
    ch = int(cw * 9 / 16)
    top = (img.height - ch) // 2
    img = img.crop((0, top, cw, top + ch)).resize((W, H), Image.LANCZOS)
    # darken + vignette so the text pops
    img = img.point(lambda p: int(p * 0.55))
    ov = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(ov)
    d.ellipse((-W * 0.25, -H * 0.45, W * 1.25, H * 1.45), fill=90)
    ov = ov.filter(ImageFilter.GaussianBlur(120))
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, ov)

    draw = ImageDraw.Draw(img)
    f_main = ImageFont.truetype(FONT, 148)
    f_sub = ImageFont.truetype(FONT, 52)
    total = sum(draw.textbbox((0, 0), t, font=f_main)[3] - draw.textbbox((0, 0), t, font=f_main)[1] for t in lines)
    y = (H - total) // 2 - 30
    for t in lines:
        bb = draw.textbbox((0, 0), t, font=f_main)
        x = (W - (bb[2] - bb[0])) // 2
        draw.text((x + 4, y + 4), t, font=f_main, fill=(0, 0, 0))
        draw.text((x, y), t, font=f_main, fill=AMBER)
        y += bb[3] - bb[1] + 26
    bb = draw.textbbox((0, 0), sub, font=f_sub)
    draw.text(((W - (bb[2] - bb[0])) // 2, y + 44), sub, font=f_sub, fill=(235, 230, 220))
    img.save(out_path, "PNG")
    print("wrote", out_path)

compose(f"{VID}/agnes-title-bg.png", f"{VID}/title-card.png",
        ["财权 FinHub"], "企业与个人的统一财务中枢")
compose(f"{VID}/agnes-end-bg.png", f"{VID}/end-card.png",
        ["你的财务部", "尽在掌握"], "FinHub — Demo Showcase")
