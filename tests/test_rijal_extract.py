"""Tests for رجال extraction from a تقريب التهذيب-style book (scripts.build_rijal)."""

from __future__ import annotations

from app.parsing.rijal_extract import iter_narrators
from app.rijal.grades import classify
from app.rijal.index import RijalIndex
from scripts.build_rijal import dedupe_against_seed, merge_source

# A faithful slice of تقريب: numbered entries, terse verdict before «من الطبقة»,
# rumūz at the end, a «[]» cross-reference to skip, a bracketed [مقبول], and the
# trap entry whose «الأولين» must NOT be read as «لين».
PAGE = "\n".join([
    "١- محمد ابن إسماعيل البخاري الإمام ثقة حافظ من الحادية عشرة مات سنة ست وخمسين ومائتين خ",
    "٢- سفيان ابن سعيد الثوري الكوفي ثقة حافظ فقيه إمام حجة من السابعة مات سنة إحدى وستين ومائة ع",
    "٣- عبد الله ابن لهيعة المصري صدوق خلط بعد احتراق كتبه من السابعة مات سنة أربع وسبعين ومائة د ت ق",
    "٤- جابر ابن يزيد الجعفي الكوفي ضعيف رافضي من الخامسة مات سنة ثمان وعشرين ومائة ت ق",
    "٥- بلال ابن رباح المؤذن مولى أبي بكر من السابقين الأولين وشهد بدرا مات سنة سبع عشرة ع",
    "٦- خالد ابن مهران البصري مقبول من الرابعة د",
    "٧- عمرو ابن دينار المكي [مقبول] من الثالثة س",
    "٨- الحارث ابن عبد الله الأعور الهمداني كذبه الشعبي من الثالثة مات سنة خمس وستين ٤",
    "٩- نوح ابن أبي مريم الجامع متروك من الثامنة ت",
    "[] فلان ابن علان يأتي في ترجمة أخرى",
    "١٠- ثابت ابن أسلم البناني البصري ثقة عابد من الرابعة مات سنة سبع وعشرين ومائة ع",
])


def _records():
    return list(iter_narrators([{"pg": 1, "text": PAGE}]))


def test_extracts_every_numbered_entry_and_skips_crossref():
    recs = _records()
    assert len(recs) == 10                                   # the «[]» line is skipped
    assert not any("يأتي في ترجمة" in r["name"] for r in recs)


def test_grades_classify_correctly():
    by_cat = {classify(r["grade"])[0] for r in _records()}
    g = {r["name"].split()[0] + " " + r["name"].split()[2]: classify(r["grade"])[0]
         for r in _records()}  # «محمد البخاري» etc. (skip «ابن»)
    cats = [classify(r["grade"])[0] for r in _records()]
    assert cats[0] == "ثقة"                  # البخاري
    assert cats[2] == "صدوق له أوهام"        # ابن لهيعة (صدوق + خلط)
    assert cats[3] == "ضعيف"                 # جابر الجعفي
    assert cats[7] == "كذاب"                 # الحارث الأعور (كذبه — narrative)
    assert cats[8] == "متروك"                # نوح الجامع
    assert "مقبول" in by_cat                 # both مقبول entries (one bracketed)


def test_companion_not_misread_as_layyin():
    """«من السابقين الأولين» must classify as صحابي, never لين (substring trap)."""
    bilal = next(r for r in _records() if r["name"].startswith("بلال"))
    assert classify(bilal["grade"])[0] == "صحابي"


def test_bracketed_verdict_is_kept():
    amr = next(r for r in _records() if r["name"].startswith("عمرو ابن دينار"))
    assert classify(amr["grade"])[0] == "مقبول"


def test_death_year_parsed():
    bukhari = next(r for r in _records() if "البخاري" in r["name"])
    assert bukhari["death_year"] == 256


def test_lookup_resolves_isnad_names():
    idx = RijalIndex(_records())
    assert idx.lookup("جابر بن يزيد الجعفي").entry.category == "ضعيف"
    assert idx.lookup("ثابت بن أسلم البناني").entry.category == "ثقة"


def test_lookup_does_not_overgrade_via_single_token_alias():
    """A different man who merely shares one ism must NOT resolve to the Companion
    (audit RIJ-1: «خالد بن عمر» was wrongly graded عمر بن الخطاب, صحابي rank 10)."""
    from app.rijal import load_seed
    idx = RijalIndex(load_seed())
    assert idx.lookup("خالد بن عمر") is None
    assert idx.lookup("محمد بن أنس") is None
    assert idx.lookup("عمر بن علي المقدمي") is None
    # but the real Companions still resolve (by full name and by bare ism in a chain)
    assert idx.lookup("عمر بن الخطاب").entry.category == "صحابي"
    assert idx.lookup("أنس").entry.category == "صحابي"
    assert idx.lookup("عن أنس").entry.category == "صحابي"


def test_dedupe_drops_exact_seed_duplicates_but_keeps_namesakes():
    records = [
        {"name": "عبد الله بن عمر", "grade": "صحابي"},            # exact seed alias → drop
        {"name": "عبد الله بن عمر العمري المكبر", "grade": "ضعيف"},  # distinct namesake → keep
        {"name": "زنفل ابن عبد الله العرفي", "grade": "ضعيف"},     # stranger → keep
    ]
    names = [r["name"] for r in dedupe_against_seed(records)]
    assert "عبد الله بن عمر" not in names           # true duplicate removed
    assert any("العمري" in n for n in names)         # the weak namesake survives, graded ضعيف
    assert any("زنفل" in n for n in names)


def test_merge_source_fills_gaps_and_adds_without_duplicating():
    # primary (تقريب): one well-graded, one left ungraded.
    primary = [
        {"name": "سفيان ابن سعيد الثوري الكوفي", "grade": "ثقة", "source": "تقريب"},
        {"name": "محمد ابن عجلان المدني", "grade": "غير محدد", "source": "تقريب"},
    ]
    # secondary (الكاشف): grades the gap, repeats the graded one, adds a new man, plus a blank.
    secondary = [
        {"name": "محمد ابن عجلان المدني القرشي", "grade": "صدوق", "source": "الكاشف"},  # → fills gap
        {"name": "سفيان ابن سعيد الثوري", "grade": "حافظ", "source": "الكاشف"},          # → dup, skip
        {"name": "هشيم ابن بشير الواسطي", "grade": "ثقة", "source": "الكاشف"},           # → new
        {"name": "رجل مبهم", "grade": "غير محدد", "source": "الكاشف"},                    # → blank, skip
    ]
    merged, added, upgraded = merge_source(primary, secondary)
    names = [r["name"] for r in merged]
    assert added == 1 and upgraded == 1
    assert any("هشيم" in n for n in names)                       # the new narrator is added
    ajlan = next(r for r in merged if r["name"].startswith("محمد ابن عجلان"))
    assert classify(ajlan["grade"])[0] == "صدوق"                 # gap filled by al-Dhahabi
    assert sum(1 for n in names if "الثوري" in n) == 1          # no duplicate الثوري
