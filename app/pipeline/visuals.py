"""Visual generation: each scene becomes a vertical 1080x1920 frame.

Fully offline using Pillow. Renders gradient backgrounds, a big overlay badge
and word-wrapped caption text with a readable shadow. This is the default
"slide" visual style; a local Stable Diffusion backend can be plugged in later
behind the same `render_scene` signature.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
import math

from PIL import Image, ImageDraw, ImageFont

# Vertical short-form format (TikTok / Reels / Shorts).
WIDTH, HEIGHT = 1080, 1920

# Color palettes per scene kind (top color, bottom color, accent).
_PALETTES = {
    "hook":  ((255, 94, 98), (255, 195, 113), (20, 20, 30)),
    "point": ((33, 147, 176), (109, 213, 237), (10, 30, 40)),
    "cta":   ((131, 58, 180), (253, 29, 29), (255, 255, 255)),
}


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _vertical_gradient(top: Tuple[int, int, int], bottom: Tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", (WIDTH, HEIGHT), top)
    draw = ImageDraw.Draw(base)
    for y in range(HEIGHT):
        t = y / HEIGHT
        # ease for a smoother blend
        t = 0.5 - 0.5 * math.cos(math.pi * t)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))
    return base


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
          max_width: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _text_with_shadow(draw, xy, text, font, fill, anchor="mm"):
    x, y = xy
    for dx, dy in ((3, 3), (-3, 3), (3, -3), (-3, -3)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0), anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def _fit_cover(im: Image.Image) -> Image.Image:
    """Resize/crop an arbitrary image to exactly WIDTHxHEIGHT (cover)."""
    src_ratio = im.width / im.height
    dst_ratio = WIDTH / HEIGHT
    if src_ratio > dst_ratio:
        new_h = HEIGHT
        new_w = int(new_h * src_ratio)
    else:
        new_w = WIDTH
        new_h = int(new_w / src_ratio)
    im = im.resize((new_w, new_h))
    left = (new_w - WIDTH) // 2
    top = (new_h - HEIGHT) // 2
    return im.crop((left, top, left + WIDTH, top + HEIGHT))


def render_scene(kind: str, text: str, overlay: str, out_path: Path,
                 index: int = 0, total: int = 1,
                 background: Path | None = None) -> Path:
    top, bottom, accent = _PALETTES.get(kind, _PALETTES["point"])
    if background and Path(background).exists():
        # AI/photo background, darkened for text legibility
        img = _fit_cover(Image.open(background).convert("RGB"))
        scrim = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        img = Image.blend(img, scrim, 0.45)
    else:
        img = _vertical_gradient(top, bottom)
    draw = ImageDraw.Draw(img)

    margin = 90
    max_w = WIDTH - 2 * margin

    # --- overlay badge (top) ---
    badge_font = _font(96)
    if overlay:
        pad = 30
        bw = draw.textlength(overlay, font=badge_font)
        bx0, by0 = margin, 150
        draw.rounded_rectangle(
            [bx0, by0, bx0 + bw + 2 * pad, by0 + 150],
            radius=30, fill=(0, 0, 0, 0) if False else accent)
        fill = (255, 255, 255) if accent != (255, 255, 255) else (20, 20, 30)
        draw.text((bx0 + pad, by0 + 25), overlay, font=badge_font, fill=fill)

    # --- main caption (center), auto-sized to fit ---
    size = 110
    while size > 48:
        cap_font = _font(size)
        lines = _wrap(draw, text, cap_font, max_w)
        line_h = int(size * 1.25)
        block_h = line_h * len(lines)
        if block_h <= HEIGHT * 0.5:
            break
        size -= 6

    y = (HEIGHT - block_h) // 2 + line_h // 2
    for line in lines:
        _text_with_shadow(draw, (WIDTH // 2, y), line, cap_font, (255, 255, 255))
        y += line_h

    # --- progress dots (bottom) ---
    if total > 1:
        dot_r, gap = 12, 40
        total_w = total * gap
        sx = (WIDTH - total_w) // 2 + gap // 2
        for i in range(total):
            cx = sx + i * gap
            cy = HEIGHT - 140
            color = (255, 255, 255) if i == index else (255, 255, 255, 90)
            draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                         fill=color if i == index else (200, 200, 200))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def storyboard(frames: List[Path], out_path: Path, cols: int = 5) -> Path:
    """Contact sheet of all frames so you can preview the whole video at a glance."""
    thumb_w = 320
    thumb_h = int(thumb_w * HEIGHT / WIDTH)
    rows = math.ceil(len(frames) / cols)
    pad = 20
    sheet = Image.new("RGB",
                      (cols * thumb_w + (cols + 1) * pad,
                       rows * thumb_h + (rows + 1) * pad),
                      (18, 18, 22))
    for i, f in enumerate(frames):
        im = Image.open(f).resize((thumb_w, thumb_h))
        r, c = divmod(i, cols)
        x = pad + c * (thumb_w + pad)
        y = pad + r * (thumb_h + pad)
        sheet.paste(im, (x, y))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, "PNG")
    return out_path
