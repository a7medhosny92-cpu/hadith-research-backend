"""Render ``docs/architecture.png`` — the four-band system overview.

A reproducible source for the architecture figure embedded in ``docs/ARCHITECTURE.md``:
the build pipeline, the canonical رجال base (the dedup engine + what one record accumulates),
the verdict-time resolution ladder (سُلّم التمييز), and the API/UI surface. Regenerate after a
structural change so the figure never drifts::

    python docs/architecture_diagram.py

Requirements (present in CI / the dev box): Pillow built with **raqm** (``PIL.features.check("raqm")``
→ Arabic shaping), and the fonts **Noto Naskh Arabic** + **DejaVu Sans**. Rendering rule learned the
hard way: Noto Naskh carries Arabic letters, Arabic digits and «:» only — NOT Latin/parentheses/
dashes/★/·. So every Arabic label is drawn with Naskh and kept PURE Arabic; all Latin/code/numbers
go through DejaVu; stars are drawn as polygons. Mixing scripts in one draw call yields tofu boxes.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NASKH = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
NASKH_B = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"
DEJA = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJA_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
OUT = Path(__file__).resolve().parent / "architecture.png"

ar = lambda s: ImageFont.truetype(NASKH, s)
arb = lambda s: ImageFont.truetype(NASKH_B, s)
la = lambda s: ImageFont.truetype(DEJA, s)
lab = lambda s: ImageFont.truetype(DEJA_B, s)

W, H = 1780, 1100
img = Image.new("RGB", (W, H), "#f6f7f9")
d = ImageDraw.Draw(img)


def box(x0, y0, x1, y1, fill, outline, w=2, r=14):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline, width=w)


def A(x, y, t, f, fill="#16181d", anchor="ra"):   # ARABIC ONLY (Naskh, RTL)
    d.text((x, y), t, font=f, fill=fill, direction="rtl", anchor=anchor)


def Ac(xc, y, t, f, fill="#16181d"):
    d.text((xc, y), t, font=f, fill=fill, direction="rtl", anchor="ma")


def L(x, y, t, f, fill="#6a6f78", anchor="la"):   # LATIN ONLY (DejaVu)
    d.text((x, y), t, font=f, fill=fill, anchor=anchor)


def Lc(xc, y, t, f, fill="#6a6f78"):
    d.text((xc, y), t, font=f, fill=fill, anchor="ma")


def arrow(x0, y0, x1, y1, col="#5b626c", w=3):
    d.line([x0, y0, x1, y1], fill=col, width=w)
    a = math.atan2(y1 - y0, x1 - x0)
    l = 11
    for s in (0.45, -0.45):
        d.line([x1, y1, x1 - l * math.cos(a - s), y1 - l * math.sin(a - s)], fill=col, width=w)


def star(cx, cy, r, fill="#d39a2e"):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.42
        an = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + rr * math.cos(an), cy + rr * math.sin(an)))
    d.polygon(pts, fill=fill)


# title
Ac(W // 2, 22, "بنية النظام: قاعدة الرجال القانونية", arb(34), "#1a2330")
Lc(W // 2, 66, "Hadith research backend  ·  architettura  ·  una base senza doppioni", la(16), "#7a818b")

# BAND 1 — build pipeline
BL, BR = 40, W - 40
y0, y1 = 96, 196
PB, PO = "#e9f0fe", "#4774c4"
segs = [("turath.io", "الكتب الخام", "download · incrementale"),
        ("parse  →  index.db", "النصوص والإسناد", "FTS5 · split isnad/matn"),
        ("build_graph", "الشبكة وتمييز المهمل", "narrators.db · muhmal · network"),
        ("build_rijal", "القاعدة القانونية", "rijal.jsonl"),
        ("audit", "تدقيق ذاتي", "isnad·matn·conflicts·nodes")]
n = len(segs)
gap = 22
bw = (BR - BL - gap * (n - 1)) / n
for i, (t, atxt, cap) in enumerate(segs):
    x = BL + i * (bw + gap)
    xc = x + bw / 2
    star_box = (t == "build_rijal")
    box(x, y0, x + bw, y1, "#fdf3df" if star_box else PB, "#c79a3a" if star_box else PO, 3 if star_box else 2)
    if star_box:
        star(x + 22, y0 + 20, 9)
    Lc(xc, y0 + 12, t, lab(15.5), "#243047")
    Ac(xc, y0 + 44, atxt, arb(20), "#1c2430")
    Lc(xc, y1 - 24, cap, la(12), "#8a7a3a" if star_box else "#7a818b")
    if i < n - 1:
        arrow(x + bw + 3, (y0 + y1) / 2, x + bw + gap - 3, (y0 + y1) / 2)

# BAND 2 — the canonical رجال base (the heart)
gx0, gy0, gx1, gy1 = 40, 224, W - 40, 612
box(gx0, gy0, gx1, gy1, "#fdf8ec", "#c79a3a", 3, 18)
star(gx1 - 30, gy0 + 28, 11)
A(gx1 - 50, gy0 + 12, "القاعدة الرجالية القانونية: رجلٌ واحدٌ لكلّ راوٍ بلا تكرار", arb(25), "#6f5320")
L(gx0 + 22, gy0 + 16, "rijal.jsonl   ·   ~19.566 narratori   ·   removable ~1", la(15), "#9a8244")

# 2a — sources (right)
sx1 = gx1 - 26
sx0 = gx1 - 360
A(sx1, gy0 + 58, "المصادر", arb(22), "#3a4250")
L(sx0, gy0 + 62, "sources", la(13), "#8b929b")
sources = [("تقريب التهذيب", "8609 · authority"), ("الكاشف للذهبي", "2171"),
           ("الإصابة للصحابة", "9767 · add-only"), ("الثقات", "96165 · add-only"),
           ("لسان الميزان", "36357 · weak men"), ("نموذجٌ لغويٌّ مساعد", "LLM · faithful")]
sy = gy0 + 94
sh = 42
sgp = 8
for t, cap in sources:
    box(sx0, sy, sx1, sy + sh, "#ffffff", "#c79a3a", 1, 9)
    A(sx1 - 12, sy + 6, t, ar(19))
    L(sx0 + 12, sy + 13, cap, la(11.5), "#9a8a55")
    sy += sh + sgp

# 2b — collapse engine (middle)
mx0, mx1 = gx0 + 470, sx0 - 40
my0, my1 = gy0 + 58, gy1 - 26
box(mx0, my0, mx1, my1, "#eaf6ee", "#3a8a57", 2, 14)
Lc((mx0 + mx1) / 2, my0 + 8, "collapse_duplicates  ·  dedup.py", lab(16), "#27623f")
Ac((mx0 + mx1) / 2, my0 + 34, "محرّك دمج التكرار: الرجل نفسه مكتوبٌ بطريقتين", ar(18), "#3a6b4e")
paths = [("تطابق الرجل", "same_man · nisba/death/kunya", False),
         ("امتداد البادئة", "prefix-extension · naqs qarina", False),
         ("نسبٌ: ثلاثة أجدادٍ متّفقة", "deep-lineage  ·  taqrib <-> kashif", True),
         ("ظلّ الكنية وابن", "kunya / ibn shadow", False),
         ("مصالحة البذرة", "reconcile_seed", False)]
py = my0 + 66
for t, cap, st in paths:
    box(mx0 + 18, py, mx1 - 18, py + 44, "#ffffff", "#c79a3a" if st else "#7bbf97", 2 if st else 1, 9)
    if st:
        star(mx1 - 30, py + 22, 8)
    A(mx1 - (46 if st else 30), py + 6, t, arb(18) if st else ar(18), "#7a5320" if st else "#22342a")
    L(mx0 + 30, py + 14, cap, la(11.5), "#5e7a68")
    py += 52
Ac((mx0 + mx1) / 2, my1 - 26, "نقطة ثبات، حُرّاسٌ: الطبقة والنسبة وتعارض الدرجة، وإلّا يُمسك ولا نختلق", ar(15.5), "#3a6b4e")

# 2c — canonical record (left)
cx0, cx1 = gx0 + 26, mx0 - 40
cy0, cy1 = gy0 + 58, gy1 - 26
box(cx0, cy0, cx1, cy1, "#ffffff", "#c79a3a", 2, 14)
Ac((cx0 + cx1) / 2, cy0 + 8, "السجلّ القانوني يجمع كلّ شيء", arb(20), "#6f5320")
fields = ["الاسم والألقاب والأسماء البديلة", "الدرجة ورأيان: تقريب والكاشف",
          "أقوال الأئمة مع الكتاب لكلّ ناقد", "الوفاة والكنية والنسب والطبقة",
          "الشيوخ والتلاميذ في الشبكة", "المصادر التي تذكره"]
fy = cy0 + 46
for t in fields:
    d.ellipse([cx1 - 26, fy + 9, cx1 - 18, fy + 17], fill="#c79a3a")
    A(cx1 - 34, fy + 2, t, ar(18.5))
    fy += 40
Lc((cx0 + cx1) / 2, cy1 - 24, "« sapere tutto sui narratori »", la(12.5), "#8a7a3a")

arrow(sx0 - 6, (gy0 + gy1) / 2 + 6, mx1 + 6, (gy0 + gy1) / 2 + 6)
arrow(mx0 - 6, (gy0 + gy1) / 2 + 6, cx1 + 6, (gy0 + gy1) / 2 + 6)

# BAND 3 — verdict-time resolution ladder
ly0, ly1 = 640, 812
box(40, ly0, W - 40, ly1, "#f1ecf8", "#7a5aa8", 2, 16)
A(W - 62, ly0 + 12, "سُلّم التمييز وقت الحكم", arb(23), "#4a3670")
L(62, ly0 + 18, "tamyiz al-muhmal  ·  analyze_isnad  ·  ogni gradino scatta dove il precedente lascia il nome invariato", la(13), "#7a6aa0")
rungs = [("المهمل", "1 · muhmal"), ("الرفقة", "2 · canon company"), ("الشبكة الموثّقة", "3 · joint resolver"),
         ("البحث المباشر", "4 · lookup +prominence"), ("الطبقة والموضع", "5 · position"), ("بوابة الدرجة", "6 · grade gate")]
rn = len(rungs)
rgap = 16
rbw = (W - 80 - rgap * rn) / rn
rx = 56
ry0, ry1 = ly0 + 58, ly1 - 22
for i, (t, cap) in enumerate(rungs):
    box(rx, ry0, rx + rbw, ry1, "#ffffff", "#7a5aa8", 1, 10)
    Ac(rx + rbw / 2, ry0 + 18, t, arb(20), "#3b2c5e")
    Lc(rx + rbw / 2, ry1 - 30, cap, lab(13.5), "#7a5aa8")
    if i < rn - 1:
        arrow(rx + rbw + 2, (ry0 + ry1) / 2, rx + rbw + rgap - 2, (ry0 + ry1) / 2, "#7a5aa8")
    rx += rbw + rgap

# BAND 4 — API / UI
uy0, uy1 = 840, 1000
box(40, uy0, W - 40, uy1, "#eef1f4", "#7c848f", 2, 16)
A(W - 62, uy0 + 12, "الواجهة: خادمٌ وواجهةٌ في ملفٍّ واحد", arb(22), "#2b3540")
L(62, uy0 + 18, "FastAPI + single-file RTL UI  ·  11 endpoint  ·  7 tab azione + 4 tab documentazione", la(13), "#7c848f")
action = ["بحث", "سؤال", "تخريج", "راوٍ", "الشبكة", "الإسناد", "دفتري", "الرواة"]
docs = ["التدقيق", "المنهجية", "البنية", "التقنية", "تدقيق المتون", "تعارض الرجال"]


def chips(items, y, col, bg):
    g = 14
    cw = (W - 80 - g * (len(items) - 1)) / len(items)
    x = 56
    for t in items:
        box(x, y, x + cw, y + 44, bg, col, 1, 10)
        Ac(x + cw / 2, y + 8, t, arb(19), "#2b3540")
        x += cw + g


chips(action, uy0 + 56, "#4774c4", "#ffffff")
chips(docs, uy0 + 106, "#7c848f", "#f7f9fb")

# footer (latin only)
star(W // 2 - 352, H - 24, 7)
Lc(W // 2, H - 31,
   "= lavoro recente (canonical base / deep-lineage)        il grafo e' 1 iterazione dietro rijal.jsonl  (build_graph step 7, build_rijal step 8)",
   la(13), "#9aa1ab")

img.save(OUT)
print("saved", OUT, img.size)
