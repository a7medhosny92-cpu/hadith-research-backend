"""Technical-deep-dive cards for the carousel — what was built and what remains, in pure Arabic
(the fonts lack Latin glyphs, so every tech term is given its Arabic description). Reuses the
shaping/layout helpers of scripts.make_social. Run: python -m scripts.make_social_tech
"""
from __future__ import annotations

from scripts.make_social import (
    W, H, BG, CARD, INK, GREEN, GREEN2, GOLD, GOLD2, MUTED, LINE, CREAM2,
    NASKH_B, NASKH_R, KUFI_B, KUFI_R, F, _s, center, right, wrap, tlen,
    base, footer, kicker, heading, star8, bullets, paragraph, save,
)

_AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar(n):
    return str(n).translate(_AR)


def flow(d, items, top=366, bot=1112):
    """A numbered vertical pipeline: gold badges on the right, head + sub to their left."""
    n = len(items)
    step = (bot - top) // (n - 1)
    bx = W - 156
    d.line((bx, top, bx, top + step * (n - 1)), fill=LINE, width=3)
    for i, (head, sub) in enumerate(items, 1):
        y = top + step * (i - 1)
        d.ellipse((bx - 27, y - 27, bx + 27, y + 27), fill=GOLD, outline=CARD, width=3)
        center(d, bx, y - 23, ar(i), F(KUFI_B, 32), CREAM2)
        right(d, bx - 58, y - 30, head, F(NASKH_B, 37), INK)
        right(d, bx - 58, y + 12, sub, F(NASKH_R, 28), MUTED)


def layers(d, items, top=336, bot=1148):
    """Stacked rounded boxes — each a layer/stage with a head and sub."""
    n = len(items)
    gap = 12
    h = (bot - top) // n - gap
    y = top
    for head, sub in items:
        d.rounded_rectangle((108, y, W - 108, y + h), radius=18, fill=CREAM2, outline=LINE, width=2)
        star8(d, W - 150, y + h // 2, 8, GOLD)
        right(d, W - 182, y + h // 2 - 38, head, F(NASKH_B, 35), GREEN2)
        right(d, W - 182, y + h // 2 + 6, sub, F(NASKH_R, 28), MUTED)
        y += h + gap


def stat_pair(d, y, a_val, a_lbl, b_val, b_lbl):
    """Two big gold figures side by side."""
    for cx, val, lbl in [(W * 3 // 4, a_val, a_lbl), (W // 4, b_val, b_lbl)]:
        center(d, cx, y, val, F(KUFI_B, 64), GOLD2)
        center(d, cx, y + 86, lbl, F(NASKH_B, 32), INK)
    d.line((150, y + 150, W - 150, y + 150), fill=LINE, width=2)


# ───────────────────────── 11) stack ─────────────────────────
def card_stack():
    img, d = base()
    kicker(d, 104, "الجانبُ التقنيُّ")
    heading(d, 198, "بنيةٌ محليّةٌ تعملُ دونَ إنترنت", 50)
    bullets(d, 326, [
        ("خادمٌ سريعٌ بلغةِ بايثون", "وواجهةٌ واحدةٌ خفيفةٌ بلا مكتباتٍ خارجيّة"),
        ("تخزينٌ كلُّه ملفّاتٌ محليّةٌ", "فهرسةٌ نصّيّةٌ ومتّجهاتٌ، بلا قاعدةِ بياناتٍ خارجيّة"),
        ("يعملُ على المعالجِ وحدَه", "بلا حاجةٍ إلى عتادٍ خاصٍّ، ويحفظُ الخصوصيّة"),
        ("كلُّ معطًى يعودُ إلى مصدرِه", "لا اختلاقَ، والنصُّ المصدرُ حاضرٌ يُراجَع"),
    ])
    footer(d)
    return save(img, "11_stack")


# ───────────────────────── 12) pipeline ─────────────────────────
def card_pipeline():
    img, d = base()
    kicker(d, 104, "خطُّ المعالجة")
    heading(d, 198, "من الكتابِ إلى الحُكمِ", 54)
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
    return save(img, "12_pipeline")


# ───────────────────────── 13) muhmal identification ─────────────────────────
def card_tamyiz():
    img, d = base()
    kicker(d, 104, "جوهرُ المحرّك")
    heading(d, 198, "تمييزُ المهملِ من السندِ", 54)
    layers(d, [
        ("قواعدُ التمييزِ", "سفيانُ عن الأعمشِ هو الثوريُّ، قاعدةُ المحدِّثين"),
        ("قرينةُ الرفقةِ", "مَن تُناسبُ رفقتُه السندَ يُرجَّحُ على الاسمِ المجرّدِ"),
        ("التكرارُ في القاعدةِ", "شيخُ الراوي يحسمُ الاسمَ المهمَلَ"),
        ("الشبكةُ الموثّقةُ", "علاقةُ الشيخِ بالتلميذِ من تهذيب والجرحِ والثقاتِ"),
        ("بوّابةُ اتفاقِ الدرجةِ", "إن اختلفوا في الحكمِ يُتوقَّفُ، ولا يُضعَّفُ"),
        ("وعند الشكِّ لا نختلِقُ", "تُعرَضُ الاحتمالاتُ كلُّها، ولا يُجزَمُ بواحدٍ"),
    ])
    footer(d)
    return save(img, "13_tamyiz")


# ───────────────────────── 14) rijal base ─────────────────────────
def card_rijal():
    img, d = base()
    kicker(d, 104, "قاعدةُ الرجالِ")
    heading(d, 196, "آلافُ الرواةِ، بلا تكرارٍ", 52)
    stat_pair(d, 318, "+٢٣٬٠٠٠", "راوٍ بدرجاتِهم", "٩", "مصادرَ للرجالِ")
    bullets(d, 520, [
        ("قاعدةٌ موحَّدةٌ بلا مكرّرٍ", "يُدمَجُ الرجلُ الواحدُ مهما تعدّدتْ صورُ اسمِه"),
        ("الرأيُ الثاني عند الاختلافِ", "إذا اختلفَ النقّادُ أُخِذَ بأنزلِ القولينِ احتياطًا"),
        ("أقوالُ الأئمّةِ بأسمائِهم", "مع الكتابِ الذي نقلَها، مجموعةً من كلِّ المصادرِ"),
    ])
    footer(d, "التقريبُ والكاشفُ والإصابةُ والثقاتُ ولسانُ الميزانِ وتهذيبُ الكمالِ وغيرُها")
    return save(img, "14_rijal")


# ───────────────────────── 15) audits ─────────────────────────
def card_audit():
    img, d = base()
    kicker(d, 104, "التدقيقُ الآليُّ")
    heading(d, 198, "يفحصُ نفسَه، حديثًا حديثًا", 50)
    bullets(d, 322, [
        ("تدقيقُ الأسانيدِ", "يُعلِّمُ كلَّ حكمٍ مشتبهٍ على راوٍ لمراجعتِه يدويًّا"),
        ("تدقيقُ المتونِ", "يكشفُ الفراغَ وإقحامَ الإسنادِ وذيلَ التخريجِ"),
        ("تعارضُ الرجالِ", "يرصدُ تضاربَ التوثيقِ والتجريحِ في الاسمِ الواحدِ"),
        ("تغطيةُ الأسانيدِ", "كم نسبةُ رجالِ السندِ المعروفينَ في القاعدةِ"),
    ])
    y = 322 + 4 * 150
    d.rounded_rectangle((110, y, W - 110, y + 100), radius=22, fill=GREEN, outline=GOLD, width=3)
    center(d, W // 2, y + 28, "أكثرُ من ٥٦٠ اختبارَ جودةٍ آليّ", F(NASKH_B, 40), CREAM2)
    footer(d)
    return save(img, "15_audit")


# ───────────────────────── 16) structural illal ─────────────────────────
def card_illal():
    img, d = base()
    kicker(d, 104, "كشفُ العللِ")
    heading(d, 198, "قرائنُ العلّةِ من شكلِ الطرقِ", 48)
    bullets(d, 318, [
        ("التفرّدُ والغرابةُ", "صحابيٌّ واحدٌ تفرّدَ به، أو لا متابعَ له"),
        ("الشذوذُ موزونًا بالدرجةِ", "مخالفةُ الأضعفِ للأوثقِ والأكثرِ شذوذٌ ظاهرٌ"),
        ("الاضطرابُ", "صيغٌ كثيرةٌ مختلفةٌ بلا لفظٍ راجحٍ"),
        ("اختلافُ الرفعِ والوقفِ", "هل تبلغُ الطرقُ النبيَّ ﷺ أم تقفُ؟"),
        ("اختلافُ الوصلِ والإرسالِ", "أصحابيٌّ سمِعَه، أم تابعيٌّ أرسلَه؟"),
    ], gap=18)
    footer(d, "إشاراتٌ للنظرِ والبحثِ، لا أحكامٌ نهائيّة")
    return save(img, "16_illal")


# ───────────────────────── 17) what remains ─────────────────────────
def card_todo():
    img, d = base()
    kicker(d, 104, "ما زال قيدَ الإنجازِ")
    heading(d, 198, "خطواتٌ تحتاجُ دعمًا وعتادًا", 50)
    bullets(d, 322, [
        ("نموذجٌ عصبيٌّ للعللِ والتخريجِ", "يحتاجُ معالجَ رسوماتٍ قويًّا لتدريبِه"),
        ("إعادةُ ترتيبٍ ذكيّةٌ للنتائجِ", "دقّةٌ أعلى في البحثِ بالمعنى"),
        ("نشرُ الأداةِ على خادمٍ للجميعِ", "ليصلَ إليها طلبةُ العلمِ في كلِّ مكانٍ"),
        ("توسيعُ مصادرِ الرواةِ المتأخّرينَ", "لإغلاقِ ما تبقّى من فجوةِ التغطيةِ"),
    ])
    footer(d, "بدعمِكم تُنجَزُ هذه الخطواتُ ويبقى المشروعُ حُرًّا")
    return save(img, "17_todo")


def main():
    out = [card_stack(), card_pipeline(), card_tamyiz(), card_rijal(),
           card_audit(), card_illal(), card_todo()]
    print("done:", len(out), "cards")


if __name__ == "__main__":
    main()
