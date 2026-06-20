"""Square 1200×1200 versions of the technical cards (LinkedIn's preferred format). Self-contained
layout tuned for the square; reuses only the SIZE-INDEPENDENT helpers of scripts.make_social
(shaping, colours, fonts, star). Run: python -m scripts.make_social_tech_sq → data/social/sq_*.png
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from scripts.make_social import (
    INK, GREEN, GREEN2, GOLD, GOLD2, MUTED, LINE, CREAM2,
    NASKH_B, NASKH_R, KUFI_B, KUFI_R, F, _s, center, right, wrap, tlen, star8,
)

W = H = 1200
BG = (247, 243, 234)
CARD = (255, 255, 255)
_AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar(n):
    return str(n).translate(_AR)


def base():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for yy in range(30, H, 24):
        for xx in range(30, W, 24):
            d.ellipse((xx, yy, xx + 1, yy + 1), fill=(236, 226, 205))
    d.rectangle((42, 42, W - 42, H - 42), outline=GOLD, width=3)
    d.rectangle((54, 54, W - 54, H - 54), outline=GOLD, width=1)
    return img, d


def ornament(d, cy):
    star8(d, W // 2, cy, 13, GOLD)
    star8(d, W // 2, cy, 6, CREAM2)
    d.line((W // 2 - 250, cy, W // 2 - 30, cy), fill=GOLD, width=2)
    d.line((W // 2 + 30, cy, W // 2 + 250, cy), fill=GOLD, width=2)


def footer(d, tag="منصّةٌ عربيّةٌ لخدمةِ السنّةِ النبويّةِ وعلومِها"):
    ornament(d, H - 128)
    center(d, W // 2, H - 100, tag, F(NASKH_R, 28), MUTED)


def kicker(d, y, text):
    f = F(NASKH_B, 32)
    w = tlen(d, text, f)
    pad = 26
    d.rounded_rectangle((W // 2 - w // 2 - pad, y, W // 2 + w // 2 + pad, y + 56), radius=28, fill=GREEN)
    center(d, W // 2, y + 6, text, f, CREAM2)


def heading(d, y, text, size=56):
    center(d, W // 2, y, text, F(KUFI_B, size), GREEN2)


def para_r(d, y, text, fnt, fill, maxw, lh):
    for ln in wrap(d, text, fnt, maxw):
        right(d, W - 138, y, ln, fnt, fill)
        y += lh
    return y


def bullets(d, y, items, gap=24):
    for head, sub in items:
        star8(d, W - 104, y + 26, 9, GOLD)
        right(d, W - 140, y, head, F(NASKH_B, 42), INK)
        y += 56
        y = para_r(d, y, sub, F(NASKH_R, 38), MUTED, W - 300, 50) + 4 + gap
    return y


def flow(d, items, top=330, bot=1006):
    n = len(items)
    step = (bot - top) // (n - 1)
    bx = W - 168
    d.line((bx, top, bx, top + step * (n - 1)), fill=LINE, width=3)
    for i, (head, sub) in enumerate(items, 1):
        y = top + step * (i - 1)
        d.ellipse((bx - 27, y - 27, bx + 27, y + 27), fill=GOLD, outline=CARD, width=3)
        center(d, bx, y - 23, ar(i), F(KUFI_B, 32), CREAM2)
        right(d, bx - 58, y - 30, head, F(NASKH_B, 38), INK)
        right(d, bx - 58, y + 12, sub, F(NASKH_R, 29), MUTED)


def layers(d, items, top=298, bot=1008):
    n = len(items)
    gap = 12
    h = (bot - top) // n - gap
    y = top
    for head, sub in items:
        d.rounded_rectangle((116, y, W - 116, y + h), radius=18, fill=CREAM2, outline=LINE, width=2)
        star8(d, W - 158, y + h // 2, 8, GOLD)
        right(d, W - 192, y + h // 2 - 38, head, F(NASKH_B, 36), GREEN2)
        right(d, W - 192, y + h // 2 + 8, sub, F(NASKH_R, 29), MUTED)
        y += h + gap


def stat_pair(d, y, a_val, a_lbl, b_val, b_lbl):
    for cx, val, lbl in [(W * 3 // 4, a_val, a_lbl), (W // 4, b_val, b_lbl)]:
        center(d, cx, y, val, F(KUFI_B, 66), GOLD2)
        center(d, cx, y + 88, lbl, F(NASKH_B, 32), INK)
    d.line((160, y + 152, W - 160, y + 152), fill=LINE, width=2)


def save(img, name):
    import os
    os.makedirs("data/social", exist_ok=True)
    p = f"data/social/{name}.png"
    img.save(p, "PNG")
    print("wrote", p)
    return p


# ───────────────────────── the 7 square cards ─────────────────────────
def c_stack():
    img, d = base()
    kicker(d, 92, "الجانبُ التقنيُّ")
    heading(d, 186, "بنيةٌ محليّةٌ تعملُ دونَ إنترنت", 52)
    bullets(d, 310, [
        ("خادمٌ سريعٌ بلغةِ بايثون", "وواجهةٌ واحدةٌ خفيفةٌ بلا مكتباتٍ خارجيّة"),
        ("تخزينٌ كلُّه ملفّاتٌ محليّةٌ", "فهرسةٌ نصّيّةٌ ومتّجهاتٌ، بلا قاعدةِ بياناتٍ خارجيّة"),
        ("يعملُ على المعالجِ وحدَه", "بلا حاجةٍ إلى عتادٍ خاصٍّ، ويحفظُ الخصوصيّة"),
        ("كلُّ معطًى يعودُ إلى مصدرِه", "لا اختلاقَ، والنصُّ المصدرُ حاضرٌ يُراجَع"),
    ])
    footer(d)
    return save(img, "sq_11_stack")


def c_pipeline():
    img, d = base()
    kicker(d, 92, "خطُّ المعالجة")
    heading(d, 186, "من الكتابِ إلى الحُكمِ", 56)
    flow(d, [
        ("تنزيلُ الكتبِ المحقّقةِ", "قابلٌ للاستئنافِ دونَ إعادة"),
        ("تحليلُ الصفحاتِ", "متنٌ وإسنادٌ وحكمٌ وبابٌ"),
        ("الفهرسةُ النصّيّةُ الكاملةُ", "بحثٌ فوريٌّ في كلِّ المتونِ"),
        ("بناءُ شبكةِ الرواةِ", "علاقاتُ الشيوخِ والتلاميذِ"),
        ("بناءُ قاعدةِ الرجالِ", "الدرجاتُ وأقوالُ الأئمّةِ"),
        ("استخراجٌ بالذكاءِ الاصطناعيِّ", "اختياريٌّ، ومُتحقَّقٌ من المصدرِ"),
        ("التدقيقُ الآليُّ", "يتجدّدُ مع كلِّ تحديثٍ"),
    ])
    footer(d, "كلُّ مرحلةٍ آمنةُ الإعادةِ، تُبنى من المصدرِ")
    return save(img, "sq_12_pipeline")


def c_tamyiz():
    img, d = base()
    kicker(d, 92, "جوهرُ المحرّك")
    heading(d, 186, "تمييزُ المهملِ من السندِ", 56)
    layers(d, [
        ("قواعدُ التمييزِ", "سفيانُ عن الأعمشِ هو الثوريُّ، قاعدةُ المحدِّثين"),
        ("قرينةُ الرفقةِ", "مَن تُناسبُ رفقتُه السندَ يُرجَّحُ على الاسمِ المجرّدِ"),
        ("التكرارُ في القاعدةِ", "شيخُ الراوي يحسمُ الاسمَ المهمَلَ"),
        ("الشبكةُ الموثّقةُ", "علاقةُ الشيخِ بالتلميذِ من تهذيب والجرحِ والثقاتِ"),
        ("بوّابةُ اتفاقِ الدرجةِ", "إن اختلفوا في الحكمِ يُتوقَّفُ، ولا يُضعَّفُ"),
        ("وعند الشكِّ لا نختلِقُ", "تُعرَضُ الاحتمالاتُ كلُّها، ولا يُجزَمُ بواحدٍ"),
    ])
    footer(d)
    return save(img, "sq_13_tamyiz")


def c_rijal():
    img, d = base()
    kicker(d, 92, "قاعدةُ الرجالِ")
    heading(d, 184, "آلافُ الرواةِ، بلا تكرارٍ", 54)
    stat_pair(d, 300, "+٢٣٬٠٠٠", "راوٍ بدرجاتِهم", "٩", "مصادرَ للرجالِ")
    bullets(d, 506, [
        ("قاعدةٌ موحَّدةٌ بلا مكرّرٍ", "يُدمَجُ الرجلُ الواحدُ مهما تعدّدتْ صورُ اسمِه"),
        ("الرأيُ الثاني عند الاختلافِ", "إذا اختلفَ النقّادُ أُخِذَ بأنزلِ القولينِ احتياطًا"),
        ("أقوالُ الأئمّةِ بأسمائِهم", "مع الكتابِ الذي نقلَها، مجموعةً من كلِّ المصادرِ"),
    ])
    footer(d, "التقريبُ والكاشفُ والإصابةُ والثقاتُ ولسانُ الميزانِ وتهذيبُ الكمالِ وغيرُها")
    return save(img, "sq_14_rijal")


def c_audit():
    img, d = base()
    kicker(d, 92, "التدقيقُ الآليُّ")
    heading(d, 186, "يفحصُ نفسَه، حديثًا حديثًا", 52)
    bullets(d, 306, [
        ("تدقيقُ الأسانيدِ", "يُعلِّمُ كلَّ حكمٍ مشتبهٍ على راوٍ لمراجعتِه يدويًّا"),
        ("تدقيقُ المتونِ", "يكشفُ الفراغَ وإقحامَ الإسنادِ وذيلَ التخريجِ"),
        ("تعارضُ الرجالِ", "يرصدُ تضاربَ التوثيقِ والتجريحِ في الاسمِ الواحدِ"),
        ("تغطيةُ الأسانيدِ", "كم نسبةُ رجالِ السندِ المعروفينَ في القاعدةِ"),
    ])
    d.rounded_rectangle((140, 930, W - 140, 1030), radius=22, fill=GREEN, outline=GOLD, width=3)
    center(d, W // 2, 958, "أكثرُ من ٥٦٠ اختبارَ جودةٍ آليّ", F(NASKH_B, 40), CREAM2)
    footer(d)
    return save(img, "sq_15_audit")


def c_illal():
    img, d = base()
    kicker(d, 92, "كشفُ العللِ")
    heading(d, 186, "قرائنُ العلّةِ من شكلِ الطرقِ", 50)
    bullets(d, 300, [
        ("التفرّدُ والغرابةُ", "صحابيٌّ واحدٌ تفرّدَ به، أو لا متابعَ له"),
        ("الشذوذُ موزونًا بالدرجةِ", "مخالفةُ الأضعفِ للأوثقِ والأكثرِ شذوذٌ ظاهرٌ"),
        ("الاضطرابُ", "صيغٌ كثيرةٌ مختلفةٌ بلا لفظٍ راجحٍ"),
        ("اختلافُ الرفعِ والوقفِ", "هل تبلغُ الطرقُ النبيَّ ﷺ أم تقفُ؟"),
        ("اختلافُ الوصلِ والإرسالِ", "أصحابيٌّ سمِعَه، أم تابعيٌّ أرسلَه؟"),
    ], gap=16)
    footer(d, "إشاراتٌ للنظرِ والبحثِ، لا أحكامٌ نهائيّة")
    return save(img, "sq_16_illal")


def c_todo():
    img, d = base()
    kicker(d, 92, "ما زال قيدَ الإنجازِ")
    heading(d, 186, "خطواتٌ تحتاجُ دعمًا وعتادًا", 52)
    bullets(d, 312, [
        ("نموذجٌ عصبيٌّ للعللِ والتخريجِ", "يحتاجُ معالجَ رسوماتٍ قويًّا لتدريبِه"),
        ("إعادةُ ترتيبٍ ذكيّةٌ للنتائجِ", "دقّةٌ أعلى في البحثِ بالمعنى"),
        ("نشرُ الأداةِ على خادمٍ للجميعِ", "ليصلَ إليها طلبةُ العلمِ في كلِّ مكانٍ"),
        ("توسيعُ مصادرِ الرواةِ المتأخّرينَ", "لإغلاقِ ما تبقّى من فجوةِ التغطيةِ"),
    ])
    footer(d, "بدعمِكم تُنجَزُ هذه الخطواتُ ويبقى المشروعُ حُرًّا")
    return save(img, "sq_17_todo")


def main():
    out = [c_stack(), c_pipeline(), c_tamyiz(), c_rijal(), c_audit(), c_illal(), c_todo()]
    print("done:", len(out), "square cards")


if __name__ == "__main__":
    main()
