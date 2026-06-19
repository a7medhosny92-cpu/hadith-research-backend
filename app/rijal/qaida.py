"""قواعد تمييز المهمل — the classical, curated disambiguations a محدّث applies when a chain cites a
homonym by a bare name: the man is fixed by his **شيخ** (whom he narrates FROM).

«سفيانُ عن عمرِو بنِ دينار» is ابنُ عيينة؛ «سفيانُ عن الأعمش/منصور» is الثوريُّ. «حمادٌ عن أيوب» is ابنُ
زيد؛ «حمادٌ عن ثابت/حميد» is ابنُ سلمة. «هشامٌ عن أبيه» is ابنُ عروة؛ «عن قتادة» is الدستوائيُّ.

These are DETERMINISTIC rules of the science — not a heuristic over the (noisy) corpus graph — so they
resolve the famous «مشترك» the graph leaves ambiguous, at high confidence. The table is intentionally
CONSERVATIVE: only DISTINCTIVE شيوخ are listed (دينار for «عمرو بن دينار», not the ambiguous «عمرو»),
and a شيخ shared by both homonyms is omitted, so an unmatched شيخ is left ambiguous (لا نختلق). Extend
by adding a `(bare ism → [(distinctive شيخ markers, full canonical name)])` qā'ida.
"""

from __future__ import annotations

from app.parsing.normalize import normalize_for_search


def _f(s: str) -> str:
    return normalize_for_search(s)


def _markers(*names: str) -> frozenset[str]:
    return frozenset(_f(n) for n in names)


# bare folded ism  →  ordered [(distinctive شيخ markers, full canonical name)]. A marker matches when it
# is a whole folded token of the شيخ (single word) or a contiguous substring of his folded name (phrase).
_QAIDA: dict[str, list[tuple[frozenset[str], str]]] = {
    _f("سفيان"): [
        (_markers("دينار", "الزهري", "المنكدر", "الزناد", "علاقة", "ابي يزيد", "صفوان بن سليم"),
         "سفيان بن عيينة"),
        (_markers("الاعمش", "منصور", "ابي اسحاق", "كهيل", "حبيب بن ابي ثابت", "السدي", "ابي حصين", "زبيد"),
         "سفيان بن سعيد الثوري"),
    ],
    _f("حماد"): [
        (_markers("ايوب", "عبيد الله بن عمر", "شنظير", "كثير بن شنظير", "يحيى بن سعيد"),
         "حماد بن زيد"),
        (_markers("ثابت", "حميد", "علي بن زيد", "قتادة", "عمار بن ابي عمار", "ابي طلحة", "العشراء",
                  "خثيم", "الجريري", "اسحاق بن عبد الله"),
         "حماد بن سلمة"),
    ],
    _f("هشام"): [
        (_markers("ابيه", "عروة", "وهب بن كيسان"), "هشام بن عروة"),
        (_markers("قتادة", "يحيى بن ابي كثير", "ابي الزبير"), "هشام الدستوائي"),
        (_markers("ابن سيرين", "محمد بن سيرين", "الحسن", "عكرمة", "حفصة بنت سيرين"), "هشام بن حسان"),
    ],
    # يحيى بن سعيد القطان (ت198, البصري ثم الكوفي) vs الأنصاري (ت143, المدني، أقدم طبقةً)
    _f("يحيى بن سعيد"): [
        (_markers("شعبة", "الثوري", "عبيد الله بن عمر", "ابن عجلان", "الاعمش", "التيمي", "مالك بن انس",
                  "ابن ابي عروبة", "هشام بن عروة"),
         "يحيى بن سعيد القطان"),
        (_markers("سعيد بن المسيب", "عمرة", "ابي امامة بن سهل", "القاسم بن محمد", "محمد بن ابراهيم",
                  "ابي بكر بن حزم", "ابي بكر بن محمد"),
         "يحيى بن سعيد الأنصاري"),
    ],
    # سليمان بن مهران الأعمش (الكوفي) vs ابن طرخان التيمي (البصري)
    _f("سليمان"): [
        (_markers("النخعي", "ابراهيم النخعي", "ابي وائل", "شقيق", "مجاهد", "زيد بن وهب", "المعرور",
                  "ابي صالح", "عمارة بن عمير", "مسلم البطين"),
         "سليمان بن مهران الأعمش"),
        (_markers("ابي عثمان", "ابي مجلز", "بكر بن عبد الله", "طرخان", "ابي العلاء"),
         "سليمان بن طرخان التيمي"),
    ],
    # خالد بن مهران الحذاء (البصري) vs ابن عبد الله الطحان الواسطي
    _f("خالد"): [
        (_markers("ابي قلابة", "عكرمة", "ابي العالية", "عبد الله بن شقيق", "مروان الاصفر"),
         "خالد بن مهران الحذاء"),
        (_markers("حصين", "يونس بن عبيد", "الشيباني", "سهيل", "عطاء بن السائب", "خالد الحذاء", "بيان"),
         "خالد بن عبد الله الطحان"),
    ],
    # جرير بن عبد الحميد الضبي الرازي (الكوفي) vs ابن حازم الأزدي (البصري)
    _f("جرير"): [
        (_markers("منصور", "مغيرة", "قابوس", "ليث", "الاعمش", "يزيد بن ابي زياد"),
         "جرير بن عبد الحميد"),
        (_markers("ايوب", "قتادة", "الحسن", "يعلى بن حكيم", "محمد بن سيرين", "الزبير بن خريت", "نافع"),
         "جرير بن حازم"),
    ],
    # الأسود بن يزيد النخعي (تابعيّ كوفيّ، عن الصحابة) vs ابن عامر شاذان (من الأتباع، عن شعبة)
    _f("الاسود"): [
        (_markers("عبد الله بن مسعود", "عائشة", "علقمة", "ابي موسى", "عمر بن الخطاب", "معاذ"),
         "الأسود بن يزيد"),
        (_markers("شعبة", "حماد بن سلمة", "اسرائيل", "زهير", "شريك", "ابي بكر بن عياش"),
         "الأسود بن عامر"),
    ],
    # إسماعيل بن أبي خالد (تابعيّ كوفيّ) — the safe branch; the «ابن علية» side carries shared شيوخ, so
    # only the bare-ابن-أبي-خالد شيوخ (قيس/الشعبي/الحكم/طارق) are encoded, the rest left «مشترك».
    _f("اسماعيل"): [
        (_markers("قيس بن ابي حازم", "الشعبي", "الحكم بن عتيبة", "طارق بن شهاب", "ابي اسحاق الشيباني"),
         "إسماعيل بن أبي خالد"),
    ],
    # زيد بن واقد القرشي الدمشقي (ثقة، شيخ الأوزاعيّ ويحيى بن حمزة وصدقة بن خالد) vs الستّيّ البصريّ (متروك):
    # the Dimashqi narrates from his SHAMI شيوخ (بسر بن عبيد الله الحضرميّ، مكحول، حرام بن حكيم، مغيث بن
    # سُميّ، خالد بن عبد الله بن حسين) — a Basran متروك never does. So «زيد بن واقد عن بسر/مكحول…» = الدمشقيّ.
    _f("زيد بن واقد"): [
        (_markers("بسر", "مكحول", "مغيث", "حرام بن حكيم", "خالد بن عبد الله"),
         "زيد بن واقد القرشي الدمشقي"),
    ],
    # يونس: الأيليُّ صاحبُ الزهريِّ (يونس بن يزيد) vs البصريُّ يونس بن عبيد (عن الحسن وابن سيرين) vs الكوفيُّ
    # يونس بن أبي إسحاق (عن أبيه السبيعيِّ). «يونس عن الزهري» = الأيليُّ — the classical mis-ID the seed warns of.
    _f("يونس"): [
        (_markers("الزهري", "ابن شهاب"), "يونس بن يزيد الأيلي"),
        (_markers("الحسن", "ابن سيرين", "محمد بن سيرين", "عمرو بن سعيد", "حميد بن هلال"),
         "يونس بن عبيد بن دينار العبدي"),
        (_markers("ابي اسحاق", "العيزار"), "يونس بن أبي إسحاق السبيعي"),
    ],
    # حجاج بن محمد المصيصيُّ الأعور (ثقة، أثبتُ الناس في ابن جريج) — «حجاج عن ابن جريج/شعبة» = المصيصيُّ؛
    # حجاج بن أبي عثمان الصوّاف (ثقة) عن يحيى بن أبي كثير. The other حجاج (ابن أرطاة مدلِّس) is left held.
    _f("حجاج"): [
        (_markers("جريج", "شعبة", "ابن جريج"), "حجاج بن محمد المصيصي"),
        (_markers("يحيى بن ابي كثير"), "حجاج بن أبي عثمان الصواف"),
    ],
    # «شعبةُ عن هشام بن يزيد عن أنس» (صحيح مسلم، ابن خزيمة) = هشام بن زيد بن أنس بن مالك (ثقة، حفيدُ أنسٍ،
    # شيخُ شعبة) — «يزيد» تحريفُ «زيد»؛ otherwise the bare matches the متروك أبو المقدام via a buried «أبي يزيد».
    _f("هشام بن يزيد"): [
        (_markers("انس", "انس بن مالك"), "هشام بن زيد بن أنس"),
    ],
}


def resolve_qaida(name: str, shaykh: str) -> str | None:
    """Resolve a homonym cited as the bare ``name`` by its ``shaykh`` (the next man on the route), via
    the curated قواعد. Returns the full canonical name, or ``None`` when no rule applies — leave it to
    the graph. Only an EXACT bare ism fires (a name already carrying a nasab/nisba is not ambiguous)."""
    rules = _QAIDA.get(_f(name).strip())
    if not rules:
        return None
    sh = _f(shaykh)
    toks = set(sh.split())
    for markers, full in rules:
        for m in markers:
            if (m in toks) if " " not in m else (m in sh):
                return full
    return None
