"""The major Companions (الصحابة) — a curated, CLOSED, documentary anchor list.

A famous صحابي must never read «مجهول» when his رجال entry happens to carry no explicit grade
(أبي بن كعب appears as just a nasab; عبد الله بن مسعود with an empty grade …). These men are the
well-established referents the muḥaddithūn name without qualification — the الخلفاء الراشدون,
العشرة المبشّرة, the المكثرون السبعة, the العبادلة, and the other widely-narrating Companions. Anchoring
an entry to one of them is **documentary, not a guess**.

Used by ``RijalIndex.add``: an entry with NO grade whose name CONTAINS one of these (multi-token,
specific) forms is graded صحابي — see ``index._is_major_companion``. The forms are deliberately ≥2
distinctive tokens (never the bare «عبد الله») and, where a name is shared with a later narrator,
carried to enough depth to disambiguate («الحسن بن علي بن أبي طالب», not the bare «الحسن بن علي»).
"""

from __future__ import annotations

MAJOR_COMPANIONS: list[str] = [
    # الخلفاء الراشدون + العشرة المبشّرة
    "أبو بكر الصديق", "عمر بن الخطاب", "عثمان بن عفان", "علي بن أبي طالب",
    "طلحة بن عبيد الله", "الزبير بن العوام", "عبد الرحمن بن عوف", "سعد بن أبي وقاص",
    "سعيد بن زيد", "أبو عبيدة بن الجراح",
    # المكثرون السبعة
    "أبو هريرة الدوسي", "عبد الله بن عمر بن الخطاب", "أنس بن مالك", "عائشة بنت أبي بكر",
    "عبد الله بن عباس", "جابر بن عبد الله", "أبو سعيد الخدري",
    # العبادلة وكبار المفتين
    "عبد الله بن عمرو بن العاص", "عبد الله بن الزبير", "عبد الله بن مسعود",
    "أبي بن كعب", "معاذ بن جبل", "زيد بن ثابت", "أبو موسى الأشعري", "أبو الدرداء",
    # كبار الصحابة المشاهير (رواةً وفقهاءً)
    "حذيفة بن اليمان", "أبو ذر الغفاري", "سلمان الفارسي", "عمار بن ياسر",
    "البراء بن عازب", "المغيرة بن شعبة", "أسامة بن زيد", "عبادة بن الصامت",
    "بلال بن رباح", "النعمان بن بشير", "عمران بن حصين", "بريدة بن الحصيب",
    "جرير بن عبد الله البجلي", "سهل بن سعد الساعدي", "أبو أيوب الأنصاري",
    "رافع بن خديج", "سلمة بن الأكوع", "عقبة بن عامر", "أبو قتادة الأنصاري",
    "واثلة بن الأسقع", "المقداد بن الأسود", "عبد الله بن أبي أوفى", "كعب بن مالك",
    "عدي بن حاتم", "عبد الله بن جعفر", "أبو بكرة الثقفي", "ثوبان مولى رسول الله",
    "الحسن بن علي بن أبي طالب", "الحسين بن علي بن أبي طالب", "عبد الله بن سلام",
    "حسان بن ثابت", "أبو رافع مولى رسول الله", "زيد بن أرقم", "أبو هريرة",
    # أمهات المؤمنين والصحابيات
    "أم سلمة", "ميمونة بنت الحارث", "حفصة بنت عمر", "صفية بنت حيي",
    "أم حبيبة", "زينب بنت جحش", "أسماء بنت أبي بكر", "أم عطية الأنصارية",
]

# The major تابعون — the well-known فقهاء/محدّثون who are ثقة **by consensus** (used the same way:
# an entry with NO grade matching one of these is graded ثقة). Deliberately limited to the UNDISPUTED
# ones — a تابعي with any real disagreement is NOT here (his own رجال grade governs). ≥2 distinctive
# tokens, never a bare ism. Anchored to ثقة (rank 9), not صحابي.
MAJOR_TABIIN: list[str] = [
    # الفقهاء السبعة بالمدينة
    "سعيد بن المسيب", "عروة بن الزبير", "القاسم بن محمد بن أبي بكر", "سالم بن عبد الله بن عمر",
    "خارجة بن زيد بن ثابت", "سليمان بن يسار", "عبيد الله بن عبد الله بن عتبة",
    # كبار المحدّثين والفقهاء
    "محمد بن مسلم بن شهاب الزهري", "الحسن البصري", "محمد بن سيرين", "عطاء بن أبي رباح",
    "مجاهد بن جبر", "طاوس بن كيسان", "عامر بن شراحيل الشعبي", "إبراهيم النخعي",
    "نافع مولى ابن عمر", "سليمان بن مهران الأعمش", "قتادة بن دعامة", "سعيد بن جبير",
    "الأسود بن يزيد", "علقمة بن قيس النخعي", "مسروق بن الأجدع", "أبو سلمة بن عبد الرحمن",
    "أبو وائل شقيق بن سلمة", "حميد الطويل", "يحيى بن سعيد الأنصاري", "محمد بن المنكدر",
    "عمرو بن دينار", "هشام بن عروة", "أبو الزناد عبد الله بن ذكوان", "ربيعة بن أبي عبد الرحمن",
    "الحكم بن عتيبة", "حماد بن أبي سليمان", "أبو إسحاق السبيعي", "منصور بن المعتمر",
    "قيس بن أبي حازم",
]

# Famous ثقات (في الصحيحين، ثقة بالإجماع) whose رجال base sometimes carries a DUPLICATE entry with a
# CORRUPTED grave grade — a متروك/كذاب leaked from a story or another man in a prose source (سير/تاريخ
# الإسلام), split from the sound entry by the grade conflict (so dedup will not merge them). There is no
# OTHER man of the name, so the grave grade is provably the corruption: an entry whose SUBJECT is one of
# these is corrected متروك/كذاب → ثقة at load (see index._anchor_grade / RijalIndex.add). CLOSED, hand-
# verified, documentary — only men with a single famous referent and NO genuine متروك namesake.
RELIABLE_DESPITE_GRAVE: list[str] = [
    "معاذ بن معاذ العنبري",   # قاضي البصرة، ت١٩٦ — ثقة بالإجماع (شيخ أحمد وابن المديني)
    "حريز بن عثمان",          # الرحبي الحمصي، ت١٦٣ — ثقة ثبت في صحيح البخاري (رُمي بالنصب لا بالكذب)
]
