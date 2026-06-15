"""Tests for الثقات ممن لم يقع في الكتب الستة extraction (app.parsing.thiqat_extract)."""

from __future__ import annotations

from app.parsing.normalize import strip_diacritics
from app.parsing.thiqat_extract import _grade_from, iter_thiqat, parse_entry


def _e(num, body, heading=None):
    return parse_entry(num, strip_diacritics(body), heading)


def test_cited_jarh_outranks_inclusion():
    """A man IN «الثقات» but graded ضعيف by a cited critic is ضعيف (الجرحُ المفسَّر مقدَّم) — and the
    named verdict is kept in appraisals."""
    rec = _e(1, "شاهين بن حيان، أخو فهد بن حيان. يروي عن شعبة. روى عنه العباس. "
                "وقال أبو حاتم: ضعيف الحديث.")
    assert rec["name"] == "شاهين بن حيان"                 # cut at the relational «أخو», no «يروي» leak
    assert rec["grade"] == "ضعيف الحديث"
    assert rec["appraisals"] == [{"critic": "أبو حاتم الرازي", "verdict": "ضعيف الحديث"}]


def test_no_cited_grade_is_thiqa_by_inclusion():
    rec = _e(2, "يروي عن ابن مسعود. روى عنه الأسود بن قيس.", "شبر بن علقمة العبدي")
    assert rec["name"] == "شبر بن علقمة العبدي" and rec["grade"] == "ثقة"
    assert rec["shuyukh"] == ["ابن مسعود"] and rec["talamidh"] == ["الأسود بن قيس"]


def test_name_from_heading_when_body_has_none():
    rec = _e(3, ". سمع وحدث. قال ابن النجار: كتبت عنه.", "عبد الواحد بن محمد البغدادي")
    assert rec is not None and rec["name"] == "عبد الواحد بن محمد البغدادي" and rec["grade"] == "ثقة"


def test_muqaddima_book_titles_are_dropped():
    # the محقق's numbered source-list — no narrator signal
    assert _e(1, "«قضاء الوطر من نزهة النظر» للقاني المالكي، طبع في ثلاثة مجلدات.") is None
    assert _e(2, "كتاب الجرح والتعديل لابن أبي حاتم.") is None


def test_grade_from_takes_the_weakest():
    assert _grade_from(["ثقة", "ضعيف"]) == "ضعيف"        # الجرح مقدّم
    assert _grade_from([]) == "ثقة"                        # inclusion


def test_iter_reads_headings_and_skips_muqaddima():
    data = {
        "indexes": {"headings": [
            {"title": "الباب الأول ترجمة المصنف", "page": 6, "level": 3},   # muqaddima — not a name
            {"title": "١٠٠ - شبر بن علقمة العبدي", "page": 278, "level": 5},
        ]},
        "pages": [
            {"pg": 278, "text": "١٠٠ - . يروي عن ابن مسعود. روى عنه الأسود بن قيس."},
        ],
    }
    recs = list(iter_thiqat(data))
    assert len(recs) == 1
    assert recs[0]["name"] == "شبر بن علقمة العبدي" and recs[0]["source"].startswith("الثقات")
