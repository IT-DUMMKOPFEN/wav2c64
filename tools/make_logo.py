"""Draw the WAV2C64 logo, app icon and header banner (needs Pillow).

    python tools/make_logo.py

Idea: C64 blue background, the classic C64 colour stripes running from
bottom left to top right, a smooth sound wave entering the stripes and
leaving them as blocky 4-bit steps - which is exactly what the app does.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "wav2c64", "assets")
FONT = os.path.join(ASSETS, "fonts", "PressStart2P-Regular.ttf")

# C64 palette ("Colodore" values)
BLUE = (0x35, 0x28, 0x79)
BLUE_DARK = (0x22, 0x19, 0x55)
LIGHT_BLUE = (0x70, 0x6d, 0xeb)
WHITE = (0xff, 0xff, 0xff)
STRIPES = [(0xc4, 0x6c, 0x71),   # light red
           (0xce, 0x8e, 0x3f),   # orange
           (0xed, 0xf1, 0x71),   # yellow
           (0xa9, 0xff, 0x9f),   # light green
           (0x75, 0xce, 0xc8)]   # cyan


def _stripes(draw, w, h, px, band_w, cx=None, cy=None):
    """45 degree stripes from bottom left to top right, as pixel steps.
    The band runs through the point (cx, cy)."""
    cx = w / 2.0 if cx is None else cx
    cy = h / 2.0 if cy is None else cy
    n = len(STRIPES)
    total = band_w * n
    for gy in range(0, h, px):
        for gx in range(0, w, px):
            d = (gx + px / 2.0 - cx) + (gy + px / 2.0 - cy)
            k = (d + total / 2.0) / band_w
            if 0 <= k < n:
                draw.rectangle([gx, gy, gx + px - 1, gy + px - 1], fill=STRIPES[int(k)])


def _thick_line(draw, pts, width, fill):
    r = width / 2.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        draw.line([(x0, y0), (x1, y1)], fill=fill, width=int(width))
    for x, y in pts:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _wave(draw, px, y0, amp, x_from, x_mid, x_to, periods, width):
    """Smooth wave from x_from to x_mid, 4-bit staircase to x_to."""
    def f(x):
        return math.sin((x - x_from) / float(x_to - x_from) * periods * 2 * math.pi)
    sh = width * 0.45
    pts = [(x, y0 - amp * f(x)) for x in range(int(x_from), int(x_mid) + 1, 3)]
    _thick_line(draw, [(x + sh, y + sh) for x, y in pts], width, BLUE_DARK)
    _thick_line(draw, pts, width, WHITE)
    # staircase: 16 levels like the C64 volume register
    step = px
    cells = []
    x = x_mid - step / 2.0
    prev = None
    while x < x_to:
        lvl = round((f(x + step / 2.0) + 1) * 7.5)
        y = y0 + amp - lvl * (2 * amp / 15.0)
        y = round(y / px) * px
        if prev is not None and prev != y:
            lo, hi = min(prev, y), max(prev, y)
            cells.append((x, lo, x + width, hi + width))
        cells.append((x, y, x + step + 1, y + width))
        prev = y
        x += step
    for c in cells:
        draw.rectangle([c[0] + sh, c[1] + sh, c[2] + sh, c[3] + sh], fill=BLUE_DARK)
    for c in cells:
        draw.rectangle(c, fill=WHITE)


def _text(draw, xy, text, size, anchor="mm", shadow=True):
    font = ImageFont.truetype(FONT, size)
    x, y = xy
    if shadow:
        off = max(2, size // 10)
        for dx in range(-off, off + 1, max(1, off // 2)):
            for dy in range(-off, off + 1, max(1, off // 2)):
                draw.text((x + dx, y + dy), text, font=font, fill=BLUE_DARK, anchor=anchor)
        draw.text((x + off * 1.6, y + off * 1.6), text, font=font, fill=BLUE_DARK, anchor=anchor)
    draw.text((x, y), text, font=font, fill=WHITE, anchor=anchor)


def _rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius, fill=255)
    return m


def make_icon(size=1024, with_text=True):
    s = size
    img = Image.new("RGB", (s, s), BLUE)
    d = ImageDraw.Draw(img)
    px = s // 32
    # subtle C64 border frame
    d.rectangle([0, 0, s - 1, s - 1], outline=BLUE_DARK, width=px)
    _stripes(d, s, s, px, band_w=s * 0.072, cx=s * 0.5, cy=s * 0.44)
    _wave(d, px, y0=s * 0.44, amp=s * 0.17, x_from=s * 0.09, x_mid=s * 0.50,
          x_to=s * 0.91, periods=2.0, width=max(px * 0.9, s // 36))
    if with_text:
        _text(d, (s / 2, s * 0.855), "WAV2C64", int(s * 0.115))
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(img, (0, 0), _rounded_mask((s, s), int(s * 0.18)))
    return out


def make_banner(w=1500, h=300):
    img = Image.new("RGB", (w, h), BLUE)
    d = ImageDraw.Draw(img)
    px = h // 30
    _stripes(d, w, h, px, band_w=h * 0.075, cx=w * 0.765, cy=h * 0.5)
    _wave(d, px, y0=h * 0.50, amp=h * 0.30, x_from=w * 0.55, x_mid=w * 0.765,
          x_to=w * 0.98, periods=2.0, width=max(px * 0.9, h // 36))
    _text(d, (w * 0.03, h * 0.43), "WAV2C64", int(h * 0.22), anchor="lm")
    font = ImageFont.truetype(FONT, int(h * 0.065))
    d.text((w * 0.034, h * 0.72), "WAV TO C64 4-BIT SAMPLES", font=font,
           fill=LIGHT_BLUE, anchor="lm")
    return img


def main():
    os.makedirs(ASSETS, exist_ok=True)
    icon = make_icon(1024)
    icon.save(os.path.join(ASSETS, "icon.png"))
    icon.save(os.path.join(ASSETS, "icon.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    make_icon(256).save(os.path.join(ASSETS, "icon_256.png"))
    make_banner().save(os.path.join(ASSETS, "banner.png"))
    print("logo written to", os.path.abspath(ASSETS))


if __name__ == "__main__":
    main()
