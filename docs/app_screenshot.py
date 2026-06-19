"""Render ``docs/app.png`` — a faithful mock of the app's launch window for the README.

No headless browser is available in CI/the container, so the figure is drawn to match the
real single-file RTL UI (``app/static/index.html``): the same parchment theme (``--bg #f7f3ea``,
``--accent #1f7a52`` green, ``--gold #a87d27``), the action + study tab bars, the search box, and
two sample result cards (a hadith with متن · إسناد · درجة · citation). Regenerate after a UI change::

    python docs/app_screenshot.py

Same rendering rule as architecture_diagram.py: Pillow built with **raqm** (Arabic shaping),
Noto Naskh for PURE-Arabic labels (Arabic letters/digits/«:» only), DejaVu for Latin/numbers/
punctuation (·, -, parens). Mixing scripts in one draw call yields tofu boxes.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NASKH = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
NASKH_B = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"
DEJA = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
OUT = Path(__file__).resolve().parent / "app.png"

ar = lambda s: ImageFont.truetype(NASKH, s)
arb = lambda s: ImageFont.truetype(NASKH_B, s)
la = lambda s: ImageFont.truetype(DEJA, s)

# theme (read from index.html)
BG, CARD, INK, ACCENT, GOLD, MUTED, LINE = (
    "#f7f3ea", "#ffffff", "#2b2620", "#1f7a52", "#a87d27", "#675d45", "#e7dec9")

W, H = 1400, 940
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def box(x0, y0, x1, y1, fill, outline=None, w=1, r=12):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline, width=w)


def A(xr, y, t, f, fill=INK):                 # ARABIC, right edge at xr (RTL)
    d.text((xr, y), t, font=f, fill=fill, direction="rtl", anchor="ra")


def Aw(t, f):                                  # width of an Arabic string
    return d.textlength(t, font=f, direction="rtl")


def Ac(xc, y, t, f, fill=INK):
    d.text((xc, y), t, font=f, fill=fill, direction="rtl", anchor="ma")


def L(x, y, t, f, fill=MUTED, anchor="la"):    # LATIN
    d.text((x, y), t, font=f, fill=fill, anchor=anchor)


# ── window chrome ──────────────────────────────────────────────────────────────
box(0, 0, W, 46, "#2b2620", r=0)
for i, c in enumerate(("#e06c5f", "#e0b44f", "#54b07f")):
    d.ellipse([22 + i * 22, 17, 34 + i * 22, 29], fill=c)
Ac(W // 2, 9, "تطبيق بحث وتحقيق الحديث", arb(20), "#f3ede0")
L(W - 24, 13, "–  ☐  ✕", la(15), "#a59c8a", anchor="ra")

# ── header ─────────────────────────────────────────────────────────────────────
A(W - 40, 64, "بحثٌ وتحقيقٌ في الحديث الشريف", arb(34), INK)
A(W - 40, 112, "متنٌ مشكولٌ، إسنادٌ، درجةٌ، تخريجٌ، رجالٌ، في عربيّةٍ فصحى، مع العزو إلى المصدر",
  ar(18), MUTED)
L(44, 70, "Hadith Research", la(15), GOLD)
L(44, 92, "/app", la(13), "#b9ad97")
d.line([40, 150, W - 40, 150], fill=LINE, width=2)

# ── action tabs (RTL pills; first is active) ─────────────────────────────────────
action = ["بحث", "سؤال", "تخريج", "راوٍ", "الإسناد", "الشبكة", "الكتب", "الرواة", "دفتري"]
x = W - 40
y = 168
for i, t in enumerate(action):
    f = arb(19)
    pad = 18
    w = Aw(t, f) + pad * 2
    if i == 0:
        box(x - w, y, x, y + 42, ACCENT, ACCENT, 1, 11)
        A(x - pad, y + 7, t, f, "#ffffff")
    else:
        box(x - w, y, x, y + 42, CARD, LINE, 1, 11)
        A(x - pad, y + 7, t, f, "#3a342a")
    x -= w + 10

# ── study tabs (smaller, muted) ──────────────────────────────────────────────────
study = ["التدقيق", "تدقيق المتون", "تعارض الرجال", "المنهجية", "البنية", "التقنية"]
x = W - 40
y = 222
for t in study:
    f = ar(16)
    pad = 13
    w = Aw(t, f) + pad * 2
    box(x - w, y, x, y + 34, "#f0ece0", LINE, 1, 9)
    A(x - pad, y + 5, t, f, MUTED)
    x -= w + 8

# ── search box ───────────────────────────────────────────────────────────────────
sy = 280
box(40, sy, W - 40, sy + 56, CARD, GOLD, 1, 13)
A(W - 24, sy + 13, "اكتب الحديثَ أو السؤالَ هنا", ar(20), "#a99f88")          # placeholder
box(54, sy + 8, 184, sy + 48, ACCENT, ACCENT, 1, 10)
Ac(119, sy + 13, "ابحث", arb(20), "#ffffff")                              # button


def grade_chip(xr, y, label, bg, fg):
    f = arb(17)
    w = Aw(label, f) + 26
    box(xr - w, y, xr, y + 32, bg, None, 0, 9)
    A(xr - 13, y + 4, label, f, fg)
    return w


def card(y0, matn, isnad, grade, gbg, gfg, cite):
    box(40, y0, W - 40, y0 + 168, CARD, LINE, 1, 14)
    # grade chip + citation (top-right)
    cw = grade_chip(W - 64, y0 + 20, grade, gbg, gfg)
    A(W - 64 - cw - 16, y0 + 24, cite, ar(16), MUTED)
    # متن
    A(W - 64, y0 + 64, matn, arb(23), INK)
    # isnad
    A(W - 64, y0 + 112, "الإسناد:", arb(16), ACCENT)
    A(W - 150, y0 + 113, isnad, ar(15.5), "#6f6650")


# ── two sample result cards ──────────────────────────────────────────────────────
card(360,
     "إنَّما الأعمالُ بالنِّيّات، وإنَّما لكلِّ امرئٍ ما نَوى",
     "الحُمَيْديُّ، عن سفيانَ، عن يحيى بنِ سعيدٍ، عن محمدِ بنِ إبراهيمَ، عن علقمةَ، عن عمرَ",
     "صحيح", "#dcefe1", "#15643f", "صحيح البخاري، رقم ١، ج١ ص٦")
card(548,
     "مَن كذَبَ عليَّ مُتعمِّدًا فَلْيَتبوَّأْ مَقعدَه من النّار",
     "أبو الوليدِ، عن شعبةَ، عن منصورٍ، عن رِبْعيِّ بنِ حِراشٍ، عن عليِّ بنِ أبي طالبٍ",
     "صحيح", "#dcefe1", "#15643f", "صحيح البخاري، رقم ١٠٦")

# ── verdict strip (الحكم على الإسناد) ─────────────────────────────────────────────
vy = 736
box(40, vy, W - 40, vy + 120, "#f1f8f4", ACCENT, 1, 14)
A(W - 64, vy + 16, "الحكم على الإسناد", arb(21), "#1b5e3f")
grade_chip(120 + Aw("صحيحٌ مُتَّصِل", arb(18)) + 26, vy + 18, "صحيحٌ مُتَّصِل", "#cdebd9", "#15643f")
A(W - 64, vy + 60, "كلُّ رجاله ثقاتٌ، والإسنادُ متّصلٌ بالسماع، مُيِّز المهملُ بالشيخ والشبكة الموثّقة",
  ar(17), "#33453c")
A(W - 64, vy + 90, "حُكمُ دراسةٍ على ظاهر الرجال والاتّصال، لا تصحيحٌ تامٌّ، فيه النظرُ في العلّة والشذوذ",
  ar(15), MUTED)

# ── footer (latin) ───────────────────────────────────────────────────────────────
L(W // 2, H - 30, "FastAPI + single-file RTL UI   ·   browser  http://localhost:8000/app   ·   "
  "native desktop window (pywebview)", la(13.5), "#9a917f", anchor="mm")

img.save(OUT)
print("saved", OUT, img.size)
