"""Tests for الإصابة extraction (app.parsing.isaba_extract) and its add-only merge."""

from __future__ import annotations

from app.parsing.isaba_extract import _clean_name, iter_isaba
from scripts.build_rijal import merge_source


def test_clean_name_drops_truncated_dangling_tail():
    # «عبد الله بن عبد» (a صحابي heading cut short) ended on a bare theophoric «عبد» → it became a
    # magnet matching every «عبد الله بن عبد …» citation; drop it. A complete name / a real bare
    # Companion (سعد بن معاذ) is kept.
    assert _clean_name("عبد الله بن عبد") is None
    assert _clean_name("عبد الله بن عبد الرحمن الأنصاري") == "عبد الله بن عبد الرحمن الأنصاري"
    assert _clean_name("سعد بن معاذ") == "سعد بن معاذ"


def _h(title: str, page: int = 1, level: int = 3) -> dict:
    return {"title": title, "page": page, "level": level}


def _book(headings: list[dict]) -> dict:
    return {"indexes": {"headings": headings}, "pages": []}


def _names(data: dict) -> list[str]:
    return [r["name"] for r in iter_isaba(data)]


def test_qism_1_and_2_yield_companions_3_and_4_are_skipped():
    data = _book([
        _h("١- القسم الأول:", 119),                       # muqaddima look-alike — before any حرف
        _h("٥- الأجوبة المشرقة على الأسئلة المفرقة", 120),  # muqaddima numbered list (a book title)
        _h("حرف الألف", 152, 2),
        _h("القسم الأول", 152),
        _h("١ - آبي اللحم الغفاري", 152, 5),
        _h("٢ ز- أبان بن سعيد بن العاص:", 153, 5),         # «ز» entry + trailing colon
        _h("القسم الثاني من حرف الألف", 303),
        _h("٣٣٣- أيمن بن أم أيمن", 303, 5),                # رؤية → still a Companion
        _h("القسم الثالث من حرف الألف", 314),
        _h("٤٠٠- الأحنف بن قيس", 314, 5),                  # مخضرم → NOT a Companion
        _h("القسم الرابع من حرف الألف", 348),
        _h("٥٠٠- أبرد بن أشرس", 348, 5),                   # وهم → NOT a Companion
    ])
    names = _names(data)
    assert names == ["آبي اللحم الغفاري", "أبان بن سعيد بن العاص", "أيمن بن أم أيمن"]
    assert all(r["grade"] == "صحابي" for r in iter_isaba(data))


def test_a_new_harf_reopens_qism_1_and_tatimma_keeps_it():
    data = _book([
        _h("حرف الألف", 152, 2),
        _h("القسم الرابع من حرف الألف", 348),
        _h("٥٠٠- أبرد بن أشرس", 348, 5),                   # قسم 4 → skipped
        _h("حرف الباء الموحدة", 384, 2),                   # a new letter opens at القسم الأول
        _h("١٢٣- بلال بن رباح", 384, 5),
        _h("تتمة القسم الأول من حرف الباء", 400),          # تتمة stays in قسم 1
        _h("١٥٠- بريدة بن الحصيب", 400, 5),
        _h("لقسم الثالث من حرف الباء", 448),               # the OCR'd «لقسم» variant still switches
        _h("٢٠٠- بشير بن كعب", 448, 5),
    ])
    assert _names(data) == ["بلال بن رباح", "بريدة بن الحصيب"]


def test_a_combined_qism_heading_takes_the_most_restrictive():
    data = _book([
        _h("حرف الدال المهملة", 4039, 3),
        _h("١- دحية بن خليفة الكلبي", 4039, 5),
        _h("القسم الثاني خال، وكذا القسم الثالث.", 4041),   # merged/empty sections → treat as قسم 3
        _h("٢- درهم بن زياد", 4041, 5),
        _h("وكذا القسم الرابع.", 4042),                     # «وكذا …» still switches → 4
        _h("٣- دينار بن عمرو", 4042, 5),
    ])
    assert _names(data) == ["دحية بن خليفة الكلبي"]


def test_alternate_kunya_run_is_stripped_keeping_the_nisba():
    data = _book([
        _h("حرف الألف", 152, 2),
        _h("القسم الأول", 152),
        _h("١- أبو الأزهر أو أبو زهير الأنماري", 152, 5),    # second كنية «أو أبو زهير» dropped
        _h("٢- أبو الأسود الجذامي", 153, 5),                 # clean كنية+nisba — kept whole
        _h("٣- دحية بن خليفة الكلبي", 154, 5),               # «خليفة» is a real name here — not cut
    ])
    assert _names(data) == ["أبو الأزهر الأنماري", "أبو الأسود الجذامي", "دحية بن خليفة الكلبي"]


def test_unusable_heads_are_dropped():
    data = _book([
        _h("حرف الميم", 2899, 2),
        _h("القسم الأول", 2899),
        _h("٨٢٠٣- مقسم", 3126, 5),                          # single token → would over-match
        _h("٨٢٠٤- مقسم، آخر:", 3126, 5),                    # «آخر» tag stripped → single token → drop
        _h("٨٢٠٥- امرأة من بني عبد الأشهل", 3130, 5),       # unnamed/relational head
        _h("٨٢٠٦- معاذ بن جبل [(١)]", 3131, 5),             # footnote ref stripped
    ])
    assert _names(data) == ["معاذ بن جبل"]


def test_merge_fill_gaps_false_is_add_only():
    primary = [{"name": "زيد بن مثقال التجريبي", "grade": "صدوق", "source": "تقريب"}]
    secondary = [
        {"name": "زيد بن مثقال التجريبي", "grade": "صحابي", "source": "الإصابة"},  # same name = known
        {"name": "وهب بن قيس التجريبي", "grade": "صحابي", "source": "الإصابة"},   # genuinely new
    ]
    result, added, upgraded = merge_source(primary, secondary, fill_gaps=False)
    assert added == 1 and upgraded == 0
    existing = next(r for r in result if r["name"] == "زيد بن مثقال التجريبي")
    assert existing["grade"] == "صدوق" and "opinions" not in existing   # untouched — no «صحابي» stamp
    assert any(r["name"] == "وهب بن قيس التجريبي" for r in result)
