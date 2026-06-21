"""Three section-divider cards for the carousel (inverted green covers that separate the
Presentation / App-in-use / Technical sections). Reuses scripts.make_social's helpers.
Run: python -m scripts.make_social_dividers
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from scripts.make_social import (
    W, H, GREEN, GREEN2, GOLD, GOLD2, CREAM2, NASKH_B, NASKH_R, KUFI_B, KUFI_R,
    F, _s, center, right, tlen, star8, save,
)

_AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
DGREEN = (15, 71, 48)          # deep green background
LIGHT = (240, 233, 216)        # light cream text
LGOLD = (226, 200, 140)        # light gold


def dbase():
    """A divider base: deep-green background, faint dot texture, gold double frame."""
    img = Image.new("RGB", (W, H), DGREEN)
    d = ImageDraw.Draw(img)
    for yy in range(30, H, 26):
        for xx in range(30, W, 26):
            d.ellipse((xx, yy, xx + 1, yy + 1), fill=(21, 84, 58))
    d.rectangle((38, 38, W - 38, H - 38), outline=GOLD, width=3)
    d.rectangle((50, 50, W - 50, H - 50), outline=(150, 120, 55), width=1)
    return img, d


def dornament(d, cy):
    star8(d, W // 2, cy, 13, GOLD)
    star8(d, W // 2, cy, 6, DGREEN)
    d.line((W // 2 - 230, cy, W // 2 - 30, cy), fill=GOLD, width=2)
    d.line((W // 2 + 30, cy, W // 2 + 230, cy), fill=GOLD, width=2)


def pill(d, y, text):
    f = F(NASKH_B, 32)
    w = tlen(d, text, f)
    pad = 26
    d.rounded_rectangle((W // 2 - w // 2 - pad, y, W // 2 + w // 2 + pad, y + 56),
                        radius=28, fill=GOLD)
    center(d, W // 2, y + 6, text, f, DGREEN)


def emblem(d, cy, r=62):
    """The project's eight-pointed-star motif, gold on green (replaces a bare number)."""
    star8(d, W // 2, cy, r, GOLD)
    star8(d, W // 2, cy, int(r * 0.54), DGREEN)
    star8(d, W // 2, cy, int(r * 0.26), GOLD)


def divider(fname, kick, title_lines, sub, items):
    img, d = dbase()
    pill(d, 116, kick)
    emblem(d, 320)
    y = 470
    for ln in title_lines:
        center(d, W // 2, y, ln, F(KUFI_B, 74), CREAM2)
        y += 98
    center(d, W // 2, y + 18, sub, F(NASKH_R, 38), LGOLD)
    dornament(d, y + 94)
    yy = y + 162
    for it in items:
        star8(d, W // 2 + tlen(d, it, F(NASKH_B, 40)) // 2 + 32, yy + 24, 8, GOLD)
        center(d, W // 2, yy, it, F(NASKH_B, 40), LIGHT)
        yy += 74
    dornament(d, H - 150)
    center(d, W // 2, H - 122, "بحثٌ وتحقيقُ الحديثِ النبويِّ", F(NASKH_R, 30), LGOLD)
    return save(img, fname)


def main():
    out = [
        divider("00_divider_intro", "القسمُ الأوّل", ["التعريفُ", "بالمشروع"],
                "ما هو، وما يقدّمه، ولماذا يستحقُّ الدعم",
                ["نظرةٌ عامّةٌ على المشروع", "الجهدُ والأرقامُ",
                 "ما الذي ينقصُ لإتمامِه", "الدعوةُ إلى الدعمِ"]),
        divider("00_divider_usage", "القسمُ الثاني", ["كيف يعملُ", "التطبيقُ"],
                "أمثلةٌ حيّةٌ من داخلِ التطبيقِ",
                ["البحثُ في السنّةِ", "تحقيقُ الإسنادِ", "بطاقةُ الراوي",
                 "التخريجُ وكشفُ العللِ", "تصفّحُ الكتبِ"]),
        divider("00_divider_tech", "القسمُ الثالث", ["الجانبُ", "التقنيُّ"],
                "كيف بُنِيَ العملُ، وما تبقّى لإتمامِه",
                ["البنيةُ وخطُّ المعالجةِ", "تمييزُ المهملِ من السندِ",
                 "قاعدةُ الرجالِ", "التدقيقُ الآليُّ وكشفُ العللِ"]),
    ]
    print("done:", len(out), "dividers")


if __name__ == "__main__":
    main()

