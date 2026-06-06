"""Grade not read from the matn; numbered bab headings aren't phantom hadiths (PARSE-2/3)."""

from __future__ import annotations

from app.parsing.grading import extract_grade
from app.parsing.hadith_extract import iter_hadith


def test_grade_needs_a_ruling_context_not_a_bare_hadith_word():
    # al-Tirmidhī's «هذا حديث حسن صحيح» is a ruling …
    assert extract_grade("هذا حديث حسن صحيح") == "حسن صحيح"
    # … but «حديث حسن» occurring inside the matn / a title is NOT a ruling
    assert extract_grade("وقال خير الكلام حديث حسن عند الناس") is None
    # the other contexts still work
    assert extract_grade("إسناده صحيح") == "صحيح"
    assert extract_grade("قال الترمذي: حسن صحيح") == "حسن صحيح"


def test_numbered_bab_heading_is_not_emitted_as_a_hadith():
    pages = [{"pg": 1, "meta": {}, "text":
              "١ - باب النية\n"
              "٢ - حدثنا قتيبة عن مالك عن النبي ﷺ قال إنما الأعمال بالنيات\n"
              "٣ - حدثنا فلان عن أنس قال الدين النصيحة"}]
    hadith = list(iter_hadith(1, pages))
    assert [h.number for h in hadith] == [2, 3]          # no phantom #1 for «باب النية»
    assert all(h.chapter == "باب النية" for h in hadith)  # the heading became the chapter
