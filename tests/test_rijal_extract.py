"""Tests for رجال extraction from a تقريب التهذيب-style book (scripts.build_rijal)."""

from __future__ import annotations

from app.parsing.rijal_extract import _trim_name, iter_narrators
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


def test_name_does_not_swallow_the_biography():
    # تقريب Companion entries put the biography (death/events/titles) right after the name;
    # the name must stop at the first biographical cue, not absorb the whole tarjama. These
    # inputs are real over-captured names observed in a built rijal.jsonl.
    assert _trim_name(
        "هند بنت أبي أمية ابن المغيرة المخزومية أم سلمة أم المؤمنين تزوجها النبي ماتت سنة"
    ) == "هند بنت أبي أمية ابن المغيرة المخزومية أم سلمة أم المؤمنين"
    assert _trim_name("أم سليم بنت ملحان ابن خالد الأنصارية والدة أنس ابن مالك") \
        == "أم سليم بنت ملحان ابن خالد الأنصارية"
    assert "الفاروق" not in _trim_name("عمر ابن الخطاب القرشي العدوي يقال له الفاروق")
    assert "ولد" not in _trim_name("عبد الله ابن صفوان الجمحي أبو صفوان المكي ولد على عهد").split()
    # a plain name (+ nasab/nisba/kunya) is left intact — no false cut
    assert _trim_name("سفيان بن سعيد الثوري أبو عبد الله") == "سفيان بن سعيد الثوري أبو عبد الله"
    assert _trim_name("مالك بن أنس") == "مالك بن أنس"


def test_companion_entry_name_is_trimmed():
    # via the full pipeline: a Companion entry's name stops before the biography.
    page = "١- أم سليم بنت ملحان الأنصارية والدة أنس ابن مالك صحابية لها أحاديث ع"
    recs = list(iter_narrators([{"pg": 1, "text": page}]))
    assert recs[0]["name"] == "أم سليم بنت ملحان الأنصارية"


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


def test_honorific_descriptors_are_stripped_for_matching():
    # «زوج النبي ﷺ» / «أم المؤمنين» are titles, not name parts — a Companion carrying them
    # in the chain must still resolve (and be graded), not show as «غير معروف».
    from app.rijal import load_seed
    idx = RijalIndex(load_seed())
    for q in ("عائشة زوج النبي صلى الله عليه وسلم", "أم المؤمنين عائشة", "عائشة"):
        m = idx.lookup(q)
        assert m is not None and m.entry.name == "عائشة بنت أبي بكر"
        assert m.entry.category == "صحابي"


def test_umm_al_muminin_is_a_shared_title_not_a_specific_wife():
    # «أم المؤمنين» is borne by every wife of the Prophet, so the GIVEN NAME must decide —
    # the bare title resolves to no one (ambiguous), never silently to عائشة.
    from app.rijal import load_seed
    idx = RijalIndex(load_seed() + [{"name": "حفصة بنت عمر", "aliases": ["حفصة"], "grade": "صحابية"}])
    assert idx.lookup("أم المؤمنين") is None
    assert idx.lookup("أم المؤمنين حفصة").entry.name == "حفصة بنت عمر"
    assert idx.lookup("حفصة أم المؤمنين").entry.name == "حفصة بنت عمر"
    assert idx.lookup("أم المؤمنين عائشة").entry.name == "عائشة بنت أبي بكر"


def test_long_name_is_not_a_magnet_for_bare_tokens():
    # A real but long name whose ancestors include common isms (أنس، معمر) must not steal
    # bare queries: «معمر» is معمر بن راشد (his own ism), not «أسباط بن … بن معمر …» (an avo).
    idx = RijalIndex([
        {"name": "معمر بن راشد", "grade": "ثقة"},
        {"name": "أسباط بن اليسع بن أنس بن معمر الذهلي أبو طاهر البصري", "grade": "مقبول"},
        {"name": "أنس بن مالك", "grade": "صحابي"},
    ])
    معمر = idx.lookup("معمر")
    assert معمر.entry.name == "معمر بن راشد" and not معمر.ambiguous   # the short ism wins
    assert idx.lookup("أنس").entry.name == "أنس بن مالك"
    assert idx.lookup("أسباط").entry.name.startswith("أسباط")        # the long name still resolves


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


def test_kashif_style_entries_extract_clean_names_and_grades():
    """al-Dhahabī's الكاشف has no طبقة and uses «سمع … وعنه …»; the verdict («الحافظ»,
    «صدوق») sits around it, and OCR sometimes glues «صدوقتوفي» (audit RIJ-3/4)."""
    page = "\n".join([
        "١- أحمد بن إبراهيم الدورقي الحافظ عن هشيم وعنه مسلم توفي ٢٤٦ م د",
        "٢- أحمد بن إسحاق الحضرمي البصري ثقة سمع عكرمة وعنه أبو خيثمة توفي ٢١١ م",
        "٣- أحمد بن إبراهيم البسري الدمشقي صدوقتوفي ٢٨٩ س",
        "٤- نوح بن أبي مريم رماه بالكذب وعنه فلان ق",
    ])
    recs = list(iter_narrators([{"pg": 1, "text": page}], source="الكاشف"))
    by = {r["name"].split()[2] if len(r["name"].split()) > 2 else r["name"]: r for r in recs}
    cats = {r["name"]: classify(r["grade"])[0] for r in recs}
    # الحافظ is read as a verdict; the name stops before it
    dorqi = next(r for r in recs if "الدورقي" in r["name"])
    assert classify(dorqi["grade"])[0] == "ثقة" and "عن" not in dorqi["name"]
    # «ثقة» before «سمع» is the verdict; the name stops at it
    assert classify(next(r for r in recs if "الحضرمي" in r["name"])["grade"])[0] == "ثقة"
    # OCR glue «صدوقتوفي» is split → صدوق
    assert classify(next(r for r in recs if "البسري" in r["name"])["grade"])[0] == "صدوق"
    # «رماه بالكذب» → كذاب (narrative liar verdict)
    assert classify(next(r for r in recs if "نوح" in r["name"])["grade"])[0] == "كذاب"


def test_truncated_and_bare_grave_entries_are_dropped():
    # Garbage that, kept, condemns sound chains: a single-token «خالد» graded صحابي (mis-grades
    # every خالد الحذاء downstream), and a *bare* ism+father given the gravest verdict — «يونس بن
    # محمد» ↦ كذاب, though the real one is the ثقة المؤدّب right beside it. A name with a nisba is
    # kept even when graded كذاب (it identifies a man); a non-grave bare grade is kept too.
    page = "\n".join([
        "١- يونس ابن محمد كذاب من العاشرة ق",                       # bare + كذاب → mis-parse, drop
        "٢- يونس ابن محمد المؤدب البغدادي ثقة ثبت من التاسعة ع",     # the real man (nisba) → keep
        "٣- خالد صحابي ع",                                          # single token → drop
        "٤- عمرو ابن دينار المكي كذاب من الثالثة س",                 # has nisba → keep despite كذاب
        "٥- معمر ابن راشد ضعيف من السابعة ع",                       # bare but not grave → keep
    ])
    names = [r["name"] for r in iter_narrators([{"pg": 1, "text": page}])]
    assert "يونس ابن محمد" not in names                       # the bare كذاب mis-parse is gone
    assert any(n.startswith("يونس ابن محمد المؤدب") for n in names)  # the real ثقة survives
    assert "خالد" not in names                                # single-token truncation dropped
    assert any(n.startswith("عمرو ابن دينار") for n in names)       # a *named* man (nisba) is kept
    assert any(n.startswith("معمر ابن راشد") for n in names)        # a non-grave bare name is kept


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


def test_prose_rijal_books_are_excluded_from_hadith_parse_but_not_terse_sources():
    # تهذيب الكمال / التهذيب are *prose* رجال books: scripts.parse must skip them (else their pages
    # pollute the hadith index — observed as «book 3722: 4859 hadith»), yet they must NOT be in
    # RIJAL_SOURCES, since build_rijal's terse extractor would mangle their flowing prose.
    from app.ingestion.catalog import RIJAL_PROSE_BOOKS, RIJAL_SOURCES
    assert 3722 in RIJAL_PROSE_BOOKS                       # تهذيب الكمال
    assert 3722 not in RIJAL_SOURCES                       # never fed to the terse extractor
    assert set(RIJAL_PROSE_BOOKS).isdisjoint(RIJAL_SOURCES)


def test_kunya_not_taken_from_a_relative():
    """Subject's own kunya only — «أبو/أبي/أم X» belonging to a relative (a father in the nasab,
    or «… خالة أبي ذر») must not be taken as the subject's kunya."""
    from app.parsing.rijal_extract import _own_kunya
    assert _own_kunya("خالد بن وهبان ابن خالة أبي ذر") is None
    assert _own_kunya("محمد بن أبي بكر الصديق التيمي") is None
    m = _own_kunya("محمد بن مسلم الزهري أبو بكر")
    assert m is not None and m.group(0) == "أبو بكر"
