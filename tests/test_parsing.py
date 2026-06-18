from app.parsing.grading import extract_grade
from app.parsing.hadith_extract import iter_hadith
from app.parsing.html_clean import (
    arabic_digits_to_int,
    clean_body,
    extract_titles,
    remove_footnote_refs,
    split_footnotes,
)
from app.parsing.isnad_matn import split_isnad_matn


# ── html_clean ────────────────────────────────────────────────────────────────
def test_arabic_digits():
    assert arabic_digits_to_int("١٢٣") == 123
    assert arabic_digits_to_int("[٧]") == 7
    assert arabic_digits_to_int("لا") is None


def test_extract_titles_and_clean_body():
    text = "<span data-type='title' id=toc-5>١ - باب النية</span> متن الحديث (^١)"
    # the heading is captured separately …
    assert extract_titles(text) == ["١ - باب النية"]
    # … and removed from the body (along with tags and footnote refs)
    assert clean_body(text) == "متن الحديث"


def test_remove_footnote_refs_keeps_diacritics():
    assert remove_footnote_refs("إِنَّمَا (^١٢) الْأَعْمَالُ") == "إِنَّمَا  الْأَعْمَالُ"


def test_split_footnotes():
    body, foot = split_footnotes("المتن\n_________\n(^١) حاشية")
    assert body.strip() == "المتن"
    assert "حاشية" in foot


# ── isnad / matn ─────────────────────────────────────────────────────────────
def test_split_by_quote():
    text = 'حدثنا فلان، قال: سمعت رسول الله ﷺ يقول: "إنما الأعمال بالنيات"'
    isnad, matn, conf = split_isnad_matn(text)
    assert conf == "quote"
    assert matn == "إنما الأعمال بالنيات"
    assert isnad.startswith("حدثنا فلان")


def test_split_by_phrase_when_no_quote():
    text = "حدثنا فلان، عن عائشة، أنها قالت: كان النبي ﷺ يفعل كذا"
    isnad, matn, conf = split_isnad_matn(text)
    assert conf == "phrase"
    assert matn == "كان النبي ﷺ يفعل كذا"
    assert "عائشة" in isnad


def test_split_after_qala_without_colon():
    # classical texts often drop the colon; the matn must still be recovered, and a
    # «قال» that only introduces another chain link must NOT be taken as the boundary.
    text = "حدثنا علي بن محمد قال حدثنا وكيع، عن قيس، قال رأيت يد طلحة شلاء يوم أحد"
    isnad, matn, conf = split_isnad_matn(text)
    assert conf == "phrase"
    assert matn == "رأيت يد طلحة شلاء يوم أحد"
    assert "وكيع" in isnad


def test_markerless_text_is_treated_as_matn():
    # a tied continuation that shares the previous isnad — no chain of its own
    isnad, matn, conf = split_isnad_matn("وكان يأمرني فأتزر فيباشرني وأنا حائض")
    assert conf == "matn-only"
    assert matn == "وكان يأمرني فأتزر فيباشرني وأنا حائض" and isnad == ""


def test_bare_chain_stays_none():
    assert split_isnad_matn("حدثنا فلان عن أنس عن أبيه")[2] == "none"


def test_stray_trailing_quote_does_not_swallow_the_matn():
    # a lone unmatched " at the end must not hijack extraction into an empty matn
    isnad, matn, conf = split_isnad_matn('حدثنا علي بن محمد قال: حدثنا وكيع، عن قيس، قال: رأيت يد طلحة شلاء "')
    assert matn == "رأيت يد طلحة شلاء"
    assert "وكيع" in isnad


def test_anna_prophet_introduces_the_matn():
    # «أنّ النبيَّ ﷺ …» with no «قال» — the matn begins at the Prophet reference
    isnad, matn, conf = split_isnad_matn(
        "حدثنا فلان، عن سالم، أن عبد الله حدثه، أن النبي ﷺ كان ينزل تحت سرحة ضخمة")
    assert conf == "phrase"
    assert matn == "النبي ﷺ كان ينزل تحت سرحة ضخمة"
    assert "سالم" in isnad and "حدثه" in isnad


def test_rimando_inherits_previous_matn():
    from app.parsing.hadith_extract import ParsedHadith, _inherit_rimandi

    def ph(text, matn):
        return ParsedHadith(book_id=1, number=0, text=text, isnad="", matn=matn,
                            matn_confidence="x", grade=None, chapter=None,
                            volume=None, page=None, page_id=None)

    hs = [ph("حدثنا فلان قال: متن الحديث الأول", "متن الحديث الأول"),
          ph("حدثنا آخر، عن ابن عمر، مثله موقوفا", ""),     # rimando → inherits
          ph("حدثنا ثالث عن أنس عن أبيه", "")]              # bare chain → stays empty
    _inherit_rimandi(hs)
    assert hs[1].matn == "متن الحديث الأول" and hs[1].matn_confidence == "ref"
    assert hs[2].matn == ""


def test_rimando_recognised_mid_text_before_an_illa_note():
    from app.parsing.hadith_extract import ParsedHadith, _inherit_rimandi

    def ph(text, matn):
        return ParsedHadith(book_id=1, number=0, text=text, isnad="", matn=matn,
                            matn_confidence="x", grade=None, chapter=None,
                            volume=None, page=None, page_id=None)

    # «نحوه» sits mid-text, followed by an علّة comment — still a parallel of the previous
    hs = [ph("حدثنا فلان قال: متن الحديث", "متن الحديث"),
          ph("حدثناه آخر، عن علي، عن النبي ﷺ نحوه. أبو حذيفة كثير الوهم لا يحكم له", "")]
    _inherit_rimandi(hs)
    assert hs[1].matn == "متن الحديث" and hs[1].matn_confidence == "ref"


# ── grading ──────────────────────────────────────────────────────────────────
def test_grade_in_context():
    assert extract_grade("... إسناده صحيح على شرط مسلم") == "صحيح"
    assert extract_grade("قال الترمذي: حسن صحيح") == "حسن صحيح"
    assert extract_grade("الحكم: [ضعيف]") == "ضعيف"


def test_no_false_positive_grade():
    # صحيح used as an adjective in the matn, not a ruling
    assert extract_grade("هذا طريق صحيح وواضح للسالكين") is None


# ── end-to-end extraction across pages ───────────────────────────────────────
FIXTURE_PAGES = [
    {
        "pg": 10,
        "meta": {"vol": "1", "page": 100, "headings": []},
        "text": (
            "<span data-type='title' id=toc-5>١ - باب النية</span>\n"
            '• [١] حدثنا الحميدي، قال: حدثنا سفيان، عن عمر، قال: سمعت رسول الله ﷺ '
            'يقول: "إنما الأعمال بالنيات (^١)\n'
            "_________\n(^١) تعليق المحقق."
        ),
    },
    {
        "pg": 11,
        "meta": {"vol": "1", "page": 101, "headings": []},
        "text": (
            'وإنما لكل امرئ ما نوى".\n'
            "• [٢] حدثنا قتيبة، عن عائشة، أنها قالت: كان النبي ﷺ يصلي. إسناده صحيح\n"
            "_________\n* [٢] [التحفة: ١٢٣]"
        ),
    },
]


def test_iter_hadith_end_to_end():
    hadiths = list(iter_hadith(7485, FIXTURE_PAGES))
    assert [h.number for h in hadiths] == [1, 2]

    h1 = hadiths[0]
    assert h1.chapter == "١ - باب النية"
    assert h1.volume == "1" and h1.page == 100  # citation = where it starts
    assert h1.matn_confidence == "quote"
    # matn was reassembled across the page break, footnote text excluded
    assert h1.matn == "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى"
    assert "تعليق" not in h1.text
    assert h1.isnad.startswith("حدثنا الحميدي")

    h2 = hadiths[1]
    assert h2.page == 101
    assert h2.matn_confidence == "phrase"
    assert h2.grade == "صحيح"
    assert "التحفة" not in h2.text  # takhrij note lived in the footnotes, excluded


# Sunan-style edition: "N -" markers, «…» matn, ⦗N⦘ page anchors, and per-hadith
# grades in <s0> tags collected in one footnote block at the page bottom.
DASH_PAGES = [
    {
        "pg": 5,
        "meta": {"vol": "1", "page": 50, "headings": []},
        "text": (
            '<span data-type="title" id=toc-1>(١) باب الطهور</span>\n'
            "١ - حَدَّثَنَا قُتَيْبَةُ، عَنْ مَالِكٍ، عَنِ النَّبِيِّ ﷺ ⦗٦⦘ قَالَ: "
            "«لَا تُقْبَلُ صَلَاةٌ بِغَيْرِ طُهُورٍ»\n"
            "٢ - حَدَّثَنَا هَنَّادٌ، عَنْ عَائِشَةَ، أَنَّهَا قَالَتْ: كَانَ النَّبِيُّ ﷺ يُحِبُّ التَّيَمُّنَ\n"
            "_________\n<s0> صحيح\n<s0> ضعيف"
        ),
    },
]


def test_iter_hadith_dash_style_with_s0_grades():
    hadiths = list(iter_hadith(1339, DASH_PAGES))
    assert [h.number for h in hadiths] == [1, 2]

    h1 = hadiths[0]
    assert h1.chapter == "(١) باب الطهور"
    assert h1.matn == "لَا تُقْبَلُ صَلَاةٌ بِغَيْرِ طُهُورٍ"  # from «…», page anchor removed
    assert "⦗" not in h1.text
    assert h1.grade == "صحيح"  # first <s0> → first hadith

    h2 = hadiths[1]
    assert h2.matn_confidence == "phrase"
    assert h2.grade == "ضعيف"  # second <s0> → second hadith


def test_hierarchical_chapter_from_headings_index():
    """With indexes.headings, the chapter is «كتاب ← باب» — unique even when the باب title is just
    «بَابٌ»: two untitled أبواب in different كتب stay distinct (the library-tab fusion fix)."""
    pages = [
        {"pg": 10, "meta": {"vol": "1", "page": 1, "headings": []},
         "text": "• [١] حدثنا الحميدي عن عمر قال سمعت النبي ﷺ يقول إنما الأعمال بالنيات."},
        {"pg": 12, "meta": {"vol": "1", "page": 3, "headings": []},
         "text": "• [٢] حدثنا قتيبة عن أنس أن النبي ﷺ صلى ركعتين."},
        {"pg": 20, "meta": {"vol": "1", "page": 10, "headings": []},
         "text": "• [٣] حدثنا مالك عن نافع عن ابن عمر أن النبي ﷺ قال خذوا."},
    ]
    headings = [
        {"page": 10, "level": 1, "title": "كتاب الإيمان"},
        {"page": 10, "level": 2, "title": "باب أمور الإيمان"},
        {"page": 12, "level": 2, "title": "بَابٌ"},
        {"page": 20, "level": 1, "title": "كتاب العلم"},
        {"page": 20, "level": 2, "title": "بَابٌ"},
    ]
    by_num = {h.number: h.chapter for h in iter_hadith(1284, pages, headings=headings)}
    assert by_num[1] == "كتاب الإيمان ← باب أمور الإيمان"
    assert by_num[2] == "كتاب الإيمان ← بَابٌ"
    assert by_num[3] == "كتاب العلم ← بَابٌ"
    assert by_num[2] != by_num[3]            # untitled «بَابٌ» in different كتب are distinct


def test_hierarchical_chapter_heading_page_not_an_exact_page_id():
    """A heading whose page isn't an exact page id (turath headings can sit a page off) must still
    open — on the next page — never be silently dropped (which would re-fuse the باب). The two-pointer
    binds every heading ≤ the current page, mirroring sair_extract's page map."""
    pages = [
        {"pg": 10, "meta": {"vol": "1", "page": 1, "headings": []},
         "text": "• [١] حدثنا الحميدي عن عمر قال سمعت النبي ﷺ يقول إنما الأعمال بالنيات."},
        {"pg": 20, "meta": {"vol": "1", "page": 10, "headings": []},
         "text": "• [٢] حدثنا قتيبة عن أنس أن النبي ﷺ صلى ركعتين."},
    ]
    headings = [
        {"page": 10, "level": 1, "title": "كتاب الإيمان"},
        {"page": 10, "level": 2, "title": "باب الأول"},
        {"page": 15, "level": 2, "title": "باب الثاني"},   # page 15 has NO page record
    ]
    by_num = {h.number: h.chapter for h in iter_hadith(1284, pages, headings=headings)}
    assert by_num[1] == "كتاب الإيمان ← باب الأول"
    assert by_num[2] == "كتاب الإيمان ← باب الثاني"   # the page-15 باب opened on page 20, not lost


def test_taliq_only_chapter_is_recovered():
    """A باب whose body is only a تعليق/أثر (no numbered hadith) is recovered as a «taliq» entry, in
    book order, with an empty isnad — so the «الكتب» tab shows the whole book (صحيح البخاري معلّقات)."""
    pages = [
        {"pg": 10, "meta": {"vol": "1", "page": 1}, "text": "• [١] حدثنا الحميدي عن عمر قال إنما الأعمال بالنيات."},
        {"pg": 11, "meta": {"vol": "1", "page": 2},   # باب 2 has only a تعليق — no «• [N]» marker
         "text": "وقال مالك بن أنس رحمه الله الدين النصيحة لله ولرسوله ولأئمة المسلمين وعامتهم."},
        {"pg": 12, "meta": {"vol": "1", "page": 3}, "text": "• [٢] حدثنا قتيبة عن أنس أن النبي ﷺ صلى."},
    ]
    headings = [
        {"page": 10, "level": 1, "title": "كتاب الإيمان"},
        {"page": 10, "level": 2, "title": "١ - باب النية"},
        {"page": 11, "level": 2, "title": "٢ - باب الدين النصيحة"},   # تعليق-only
        {"page": 12, "level": 2, "title": "٣ - باب الصلاة"},
    ]
    out = list(iter_hadith(1284, pages, headings=headings))
    taliq = [h for h in out if h.kind == "taliq"]
    assert len(taliq) == 1
    t = taliq[0]
    assert t.chapter == "كتاب الإيمان ← ٢ - باب الدين النصيحة"
    assert t.number is None and t.isnad == "" and t.sort == 1   # ordered after hadith #1
    assert "النصيحة" in t.matn and "باب" not in t.matn.split()[:1]   # body kept, heading line stripped
    # the hadith أبواب are NOT duplicated as taliq
    assert [h.chapter for h in out if h.kind == "hadith"] == [
        "كتاب الإيمان ← ١ - باب النية", "كتاب الإيمان ← ٣ - باب الصلاة"]


def test_taliq_not_emitted_when_baab_has_hadith():
    """A باب that has a numbered hadith on a shared page is never also emitted as a تعليق."""
    pages = [
        {"pg": 10, "meta": {"vol": "1", "page": 1},
         "text": "وقال مالك تمهيد للباب.\n• [١] حدثنا الحميدي عن عمر قال إنما الأعمال بالنيات."},
    ]
    headings = [
        {"page": 10, "level": 1, "title": "كتاب الإيمان"},
        {"page": 10, "level": 2, "title": "١ - باب النية"},
    ]
    out = list(iter_hadith(1284, pages, headings=headings))
    assert all(h.kind == "hadith" for h in out)   # the باب has hadith #1 → no spurious تعليق
