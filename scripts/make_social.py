"""Generate professional Arabic social-media cards (a 5-image carousel) inviting the community to
support the Hadith-research project. Pure PIL (libraqm handles Arabic shaping + RTL bidi — pass RAW
logical strings, NO manual reshape/bidi). Run: python -m scripts.make_social  → data/social/*.png
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
NASKH_B = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"
NASKH_R = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
KUFI_B = "/usr/share/fonts/truetype/noto/NotoKufiArabic-Bold.ttf"
KUFI_R = "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf"

BG = (247, 243, 234)
CARD = (255, 255, 255)
INK = (43, 38, 32)
GREEN = (31, 122, 82)
GREEN2 = (18, 84, 56)
GOLD = (168, 125, 39)
GOLD2 = (135, 101, 22)
MUTED = (120, 108, 82)
LINE = (228, 216, 190)
CREAM2 = (251, 247, 238)


def F(path, size):
    return ImageFont.truetype(path, size)


# Noto Naskh/Kufi lack Latin/ASCII punctuation (— + ( ) … / · -) — they render as tofu. Replace every
# such char with an Arabic-friendly one (or drop it); «+» and the CTA line are DRAWN with PIL instead.
_REPL = {"—": "،", "–": "،", "-": "،", "(": "", ")": "", "…": "", "/": "، ", "·": "،", "+": ""}


def _s(t):
    for a, b in _REPL.items():
        t = t.replace(a, b)
    return t.replace(" ،", "،").replace(" .", ".").replace("،،", "،")


try:
    from fontTools.ttLib import TTFont as _TTF
    _CMAP = set(_TTF(NASKH_R)["cmap"].getBestCmap())
except Exception:  # pragma: no cover - fontTools optional
    _CMAP = None


def _check(t):
    """Warn if any glyph would be missing from Noto Naskh (a tofu box)."""
    if _CMAP is None:
        return
    bad = {c for c in t if c.strip() and ord(c) not in _CMAP and ord(c) not in (0x66C, 0x66B)}
    if bad:
        print("  ⚠ missing glyphs:", bad, "in", repr(t[:40]))


def F_(path, size):
    return ImageFont.truetype(path, size)


def tlen(d, text, fnt):
    return d.textlength(_s(text), font=fnt, direction="rtl", features=["+kern"])


def plus_mark(d, xr, ycen, size, color):
    """A drawn «+» (the font lacks one), its RIGHT edge at xr, centred on ycen. Returns its left x."""
    t = max(2, size // 5)
    half = size // 2
    cx = xr - half
    d.rounded_rectangle((cx - half, ycen - t, cx + half, ycen + t), radius=t, fill=color)
    d.rounded_rectangle((cx - t, ycen - half, cx + t, ycen + half), radius=t, fill=color)
    return cx - half


def wrap(d, text, fnt, maxw):
    text = _s(text)
    out, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if tlen(d, trial, fnt) <= maxw or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def center(d, cx, y, text, fnt, fill):
    text = _s(text)
    _check(text)
    d.text((cx, y), text, font=fnt, fill=fill, direction="rtl", anchor="ma", features=["+kern"])


def right(d, xr, y, text, fnt, fill):
    text = _s(text)
    _check(text)
    d.text((xr, y), text, font=fnt, fill=fill, direction="rtl", anchor="ra", features=["+kern"])


def dots(d):
    for yy in range(40, H, 26):
        for xx in range(40, W, 26):
            d.point((xx, yy), fill=(GOLD[0], GOLD[1], GOLD[2]))
    # too subtle as points; overlay a faint tint instead handled by caller


def star8(d, cx, cy, r, fill):
    """An eight-pointed star (خاتم سليمان) = two overlapping squares."""
    import math
    for off in (0, math.pi / 4):
        pts = [(cx + r * math.cos(off + i * math.pi / 2), cy + r * math.sin(off + i * math.pi / 2))
               for i in range(4)]
        d.polygon(pts, fill=fill)


def base():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # faint dot texture
    for yy in range(30, H, 24):
        for xx in range(30, W, 24):
            d.ellipse((xx, yy, xx + 1, yy + 1), fill=(236, 226, 205))
    # double gold frame
    d.rectangle((38, 38, W - 38, H - 38), outline=GOLD, width=3)
    d.rectangle((50, 50, W - 50, H - 50), outline=(GOLD[0], GOLD[1], GOLD[2]), width=1)
    return img, d


def ornament(d, cy):
    """A centred star flanked by two gold rules."""
    star8(d, W // 2, cy, 13, GOLD)
    star8(d, W // 2, cy, 6, CREAM2)
    d.line((W // 2 - 230, cy, W // 2 - 30, cy), fill=GOLD, width=2)
    d.line((W // 2 + 30, cy, W // 2 + 230, cy), fill=GOLD, width=2)


def footer(d, tagline="منصّةٌ عربيّةٌ لخدمةِ السنّةِ النبويّةِ وعلومِها"):
    ornament(d, H - 150)
    center(d, W // 2, H - 122, tagline, F(NASKH_R, 30), MUTED)


def kicker(d, y, text):
    """A small green pill label at the top."""
    f = F(NASKH_B, 32)
    w = tlen(d, text, f)
    pad = 26
    x0, x1 = W // 2 - w // 2 - pad, W // 2 + w // 2 + pad
    d.rounded_rectangle((x0, y, x1, y + 56), radius=28, fill=GREEN)
    center(d, W // 2, y + 6, text, f, CREAM2)


def heading(d, y, text, size=78, fill=GREEN2):
    center(d, W // 2, y, text, F(KUFI_B, size), fill)


def paragraph(d, y, text, fnt, fill, maxw=W - 220, lh=None, align="center"):
    lines = wrap(d, text, fnt, maxw)
    lh = lh or int(fnt.size * 1.7)
    for ln in lines:
        if align == "center":
            center(d, W // 2, y, ln, fnt, fill)
        else:
            right(d, W - 110, y, ln, fnt, fill)
        y += lh
    return y


def bullets(d, y, items, gap=26):
    f = F(NASKH_R, 40)
    for head, sub in items:
        # gold star marker on the right
        star8(d, W - 96, y + 26, 9, GOLD)
        right(d, W - 130, y, head, F(NASKH_B, 42), INK)
        y += 56
        if sub:
            yy = paragraph(d, y, sub, f, MUTED, maxw=W - 260, lh=52, align="right")
            y = yy + 4
        y += gap
    return y


def stat_row(d, y, value, label, plus=False):
    """A big gold number on the right of its label; an optional DRAWN «+» (font lacks one)."""
    fv = F(KUFI_B, 66)
    right(d, W - 110, y, value, fv, GOLD2)
    if plus:
        vw = tlen(d, value, fv)
        plus_mark(d, int(W - 110 - vw - 16), y + 40, 34, GOLD2)
    right(d, W - 360, y + 14, label, F(NASKH_B, 40), INK)
    d.line((140, y + 96, W - 110, y + 96), fill=LINE, width=2)
    return y + 128


def save(img, name):
    os.makedirs("data/social", exist_ok=True)
    p = f"data/social/{name}.png"
    img.save(p, "PNG")
    print("wrote", p)
    return p


# ───────────────────────── the five cards ─────────────────────────
def card1_hero():
    img, d = base()
    star8(d, W // 2, 250, 40, GOLD)
    star8(d, W // 2, 250, 22, BG)
    star8(d, W // 2, 250, 12, GOLD)
    heading(d, 360, "بحثٌ وتحقيقُ", 94)
    heading(d, 478, "الحديثِ النبويِّ", 94)
    ornament(d, 648)
    paragraph(d, 712, "منصّةٌ عربيّةٌ ذكيّةٌ للبحثِ في كتبِ السنّةِ، وتحقيقِ الأسانيدِ، "
                      "ومعرفةِ الرواةِ ودرجاتِهم، والتخريجِ وكشفِ العللِ.",
              F(NASKH_R, 46), INK, lh=80)
    d.rounded_rectangle((W // 2 - 320, 980, W // 2 + 320, 1066), radius=44, fill=GREEN)
    center(d, W // 2, 994, "ساهمْ في إتمامِ المشروعِ", F(NASKH_B, 48), CREAM2)
    center(d, W // 2, 1100, "عملٌ تطوّعيٌّ خالصٌ لخدمةِ علمِ الحديثِ", F(NASKH_R, 34), MUTED)
    footer(d)
    return save(img, "1_hero")


def card2_what():
    img, d = base()
    kicker(d, 110, "ما هذا المشروع؟")
    heading(d, 210, "أداةٌ واحدةٌ تجمعُ علمَ الحديثِ", 56)
    y = paragraph(d, 320, "برنامجٌ يعملُ على جهازِكَ دونَ إنترنت، يضعُ بينَ يديكَ السنّةَ "
                          "وعلومَها بالعربيةِ الفصحى:", F(NASKH_R, 40), MUTED, lh=58)
    bullets(d, y + 24, [
        ("بحثٌ دلاليٌّ في كتبِ السنّةِ", "تجدُ الحديثَ بالمعنى لا باللفظِ فحسب"),
        ("تحقيقُ الإسنادِ والحكمُ عليه", "تمييزُ المهملِ، واتّصالُ السندِ، ودرجةُ رواتِه"),
        ("معرفةُ الرواةِ ودرجاتِهم", "أكثرُ من ٢٣٬٠٠٠ راوٍ بأقوالِ أئمّةِ الجرحِ والتعديلِ"),
        ("التخريجُ وكشفُ العللِ", "جمعُ الطرقِ، وقرائنُ الشذوذِ والعلّةِ البنيويّةِ"),
    ])
    footer(d)
    return save(img, "2_what")


def card3_effort():
    img, d = base()
    kicker(d, 110, "جهدٌ وعملٌ")
    heading(d, 210, "أشهرٌ من العملِ المتواصلِ", 58)
    paragraph(d, 312, "بُنيَ سطرًا سطرًا، ومُحِّصَ على المطبوعِ، واختُبِرَ بدقّةٍ:",
              F(NASKH_R, 38), MUTED, lh=56)
    y = 430
    y = stat_row(d, y, "٨٤٬٠٠٠", "حديثٍ مُفهرَسٍ من كتبِ السنّةِ", plus=True)
    y = stat_row(d, y, "٢٣٬٠٠٠", "راوٍ بدرجاتِهم وأقوالِ الأئمّةِ", plus=True)
    y = stat_row(d, y, "٩٤٪", "تغطيةُ رجالِ الأسانيدِ")
    y = stat_row(d, y, "٥٦٠", "اختبارَ جودةٍ آليٍّ للتحقّقِ", plus=True)
    y = stat_row(d, y, "مئاتُ", "الساعاتِ من التطويرِ والتدقيقِ")
    footer(d)
    return save(img, "3_effort")


def card4_missing():
    img, d = base()
    kicker(d, 110, "ماذا ينقصُ لإتمامِه؟")
    heading(d, 210, "بقيَتْ خطواتٌ تحتاجُ دعمَكم", 54)
    y = paragraph(d, 320, "الأساسُ قائمٌ ويعملُ، وما تبقّى يحتاجُ وقتًا وعتادًا حاسوبيًّا:",
                  F(NASKH_R, 40), MUTED, lh=58)
    bullets(d, y + 24, [
        ("نموذجٌ ذكيٌّ لكشفِ العللِ والشذوذِ", "يحتاجُ عتادًا حاسوبيًّا قويًّا لتدريبِه"),
        ("توسيعُ قاعدةِ الرواةِ المتأخّرين", "لتغطيةِ بقيّةِ مَن خرجَ عن الكتبِ الستّةِ"),
        ("إتاحتُه للجميعِ على الشبكةِ", "خادمٌ يحملُ الأداةَ ليستفيدَ منها طلبةُ العلمِ"),
        ("تحسينُ الواجهةِ وتجربةِ الاستخدامِ", "ليكونَ سهلًا في متناولِ كلِّ باحثٍ"),
    ])
    footer(d)
    return save(img, "4_missing")


def card5_cta():
    img, d = base()
    kicker(d, 110, "لماذا يستحقُّ الدعمَ؟")
    heading(d, 210, "شراكةٌ في خدمةِ السنّةِ", 58)
    y = bullets(d, 330, [
        ("صدقةٌ جاريةٌ وعلمٌ يُنتفَعُ به", "حفظُ الإسنادِ وصيانةُ الروايةِ خدمةٌ للأمّةِ"),
        ("مجّانيٌّ ومفتوحٌ للجميعِ", "لا إعلاناتٍ ولا اشتراكاتٍ — وقفٌ لطلبةِ العلمِ"),
        ("عملٌ مستقلٌّ خالصٌ", "دعمُكم يُسرّعُ إكمالَه ويُبقيه حُرًّا"),
    ], gap=20)
    box_t = y + 12
    d.rounded_rectangle((110, box_t, W - 110, box_t + 210), radius=28, fill=GREEN, outline=GOLD, width=3)
    center(d, W // 2, box_t + 52, "كُنْ شريكًا في الأجرِ", F(KUFI_B, 58), CREAM2)
    center(d, W // 2, box_t + 142, "والدالُّ على الخيرِ كفاعلِه", F(NASKH_B, 40), (240, 233, 216))
    footer(d, "جزى اللهُ خيرًا كلَّ مَن دعمَ أو نشرَ")
    return save(img, "5_support")


def main():
    paths = [card1_hero(), card2_what(), card3_effort(), card4_missing(), card5_cta()]
    print("done:", len(paths), "cards")


if __name__ == "__main__":
    main()
