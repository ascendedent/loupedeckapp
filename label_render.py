"""Draw text labels onto device key images (Pillow).

Used by DeviceController to render a control's label directly onto the image it
pushes to the CT's screens, so labels show on the hardware as well as in the
on-screen mirror. A label is a dict: {"text", "pos": top|middle|bottom,
"mode": over|bar}.
"""

import os
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = None


def _font_path():
    global _FONT_PATH
    if _FONT_PATH is not None:
        return _FONT_PATH
    path = ""
    fc = shutil.which("fc-match")
    if fc:
        try:
            out = subprocess.run([fc, "-f", "%{file}", "sans:bold"],
                                 capture_output=True, text=True, timeout=2)
            path = out.stdout.strip()
        except Exception:
            path = ""
    if not path or not os.path.exists(path):
        for p in ("/usr/share/fonts/google-noto/NotoSans-Bold.ttf",
                  "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            if os.path.exists(p):
                path = p
                break
    _FONT_PATH = path or ""
    return _FONT_PATH


def _load_font(size):
    p = _font_path()
    if p:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _measure(draw, text, font):
    try:
        b = draw.textbbox((0, 0), text, font=font)
        return b[2] - b[0], b[3] - b[1]
    except Exception:
        return draw.textlength(text, font=font), size_guess(font)


def size_guess(font):
    try:
        return font.size
    except Exception:
        return 12


def _rgb(s, default=(0, 0, 0)):
    """'#rrggbb' (or '#aarrggbb') -> (r, g, b); default on anything unparsable."""
    s = str(s or "").lstrip("#")
    if len(s) == 8:      # #aarrggbb -> drop alpha
        s = s[2:]
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return default


def draw_label(img, label, bg_color=None):
    """Draw ``label`` onto ``img`` (a PIL RGBA image) in place and return it.

    ``label`` is {"text", "pos": top|middle|bottom, "mode": over|bar|shrink,
    "bar_color"?: "#rrggbb"}. In ``shrink`` mode the picture is resized into the
    area beside a solid label band (no overlap); ``bar``/``shrink`` fill the band
    with ``bar_color`` (default translucent black). ``bg_color`` fills behind the
    shrunk image. No-op if there is no label text.
    """
    label = label or {}
    text = (label.get("text") or "").strip()
    if not text:
        return img
    pos = label.get("pos", "bottom")
    mode = label.get("mode", "over")
    bar_rgb = _rgb(label["bar_color"]) if label.get("bar_color") else None
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    fs = max(10, int(min(w, h) / 5))
    font = _load_font(fs)
    tw, th = _measure(draw, text, font)
    # shrink to fit width
    while tw > w - 6 and fs > 9:
        fs -= 1
        font = _load_font(fs)
        tw, th = _measure(draw, text, font)
    # truncate with ellipsis if still too wide
    if tw > w - 4 and len(text) > 1:
        while len(text) > 1:
            cand = text[:-1] + "…"
            cw, th = _measure(draw, cand, font)
            text = text[:-1]
            tw = cw
            if cw <= w - 4:
                text = cand
                break
        else:
            text = text + "…"

    x = max(0, (w - tw) // 2)
    pad = 3
    # keep clear of the physical bezel between keys; the bottom edge needs more
    # clearance (labels were getting cut off there). Every mode uses this same
    # text y so shrink/bar/over all clear the bezel identically.
    top_margin = max(6, h // 9)
    bot_margin = max(12, h // 6)
    if pos == "top":
        y = top_margin
    elif pos == "middle":
        y = max(0, (h - th) // 2)
    else:
        y = max(0, h - th - bot_margin)

    if mode == "shrink":
        # shrink the picture into the area beside a solid label band; the band
        # runs from the text to the near edge, so the text keeps its bezel margin
        base = _rgb(bg_color) if bg_color else (0, 0, 0)
        band_fill = (bar_rgb + (255,)) if bar_rgb else (base + (255,))
        content = img.copy()
        draw.rectangle([0, 0, w, h], fill=base + (255,))
        if pos == "top":
            band_top, band_bot = 0, y + th + pad
            img_top, img_bot = band_bot, h
        else:                                   # bottom (middle is coerced to over)
            band_top, band_bot = max(0, y - pad), h
            img_top, img_bot = 0, band_top
        # fit the picture into the image region (preserve aspect, no distortion)
        region_h = max(1, img_bot - img_top)
        sc = min(w / content.width, region_h / content.height)
        nw, nh = max(1, round(content.width * sc)), max(1, round(content.height * sc))
        fitted = content.resize((nw, nh), Image.LANCZOS)
        img.paste(fitted, ((w - nw) // 2, img_top + (region_h - nh) // 2), fitted)
        draw.rectangle([0, band_top, w, band_bot], fill=band_fill)
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        return img

    if mode == "bar":
        draw.rectangle([0, y - pad, w, y + th + pad],
                       fill=(bar_rgb + (220,)) if bar_rgb else (0, 0, 0, 200))
    else:
        # drop shadow for legibility over arbitrary images
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 220))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    return img
