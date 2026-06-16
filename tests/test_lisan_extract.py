"""لسان الميزان extractor — app.parsing.lisan_extract (the weak/criticised non-Six men)."""

from __future__ import annotations

from app.parsing.lisan_extract import _grade_from, _heading_names, parse_entry


def test_heading_strips_the_ramz_and_number():
    data = {"indexes": {"headings": [
        {"title": "١ - ز - أبان بن أرقم الأسدي الكوفي", "level": 3},   # «ز» = زيادات ابن حجر
        {"title": "٥ - أبان بن جبلة الكوفي أبو عبد الرحمن", "level": 3},  # no رمز
        {"title": "ذ - أبان بن جعفر النجيرمي", "level": 3},             # no number → unmappable
    ]}}
    names = _heading_names(data)
    assert names[1] == "أبان بن أرقم الأسدي الكوفي"   # the «ز - » رمز is stripped, number gone
    assert names[5].startswith("أبان بن جبلة")
    assert 0 not in names                              # a رمز-only heading (no number) isn't mapped


def test_parse_entry_network_and_verdict():
    # لسان writes تلاميذ as the abbreviated «وعنه …» (not الجرح's «روى عنه»)
    body = ("رجال الطوسي روى عن ابي هاشم ومحمد بن المطلب واسماعيل بن ابي خالد "
            "وعنه خلف بن خليفة ووهب بن بقية. قال ابن ابي حاتم: مجهول. وذكره ابن حبان في الثقات.")
    rec = parse_entry(3, body, "ابان بن ارقم العتري الكوفي")
    assert rec["name"] == "ابان بن ارقم العتري الكوفي"            # name from the (clean) heading
    assert "ابي هاشم" in rec["shuyukh"] and "اسماعيل بن ابي خالد" in rec["shuyukh"]
    assert "خلف بن خليفة" in rec["talamidh"] and "وهب بن بقية" in rec["talamidh"]
    assert rec["grade"] == "مجهول"                                # the cited جرح, not «ثقة» by inclusion
    assert rec["source"].startswith("لسان الميزان")


def test_grade_is_the_cited_verdict_else_unknown():
    assert _grade_from([]) == "غير معروف"                         # الضعفاء: no inclusion-grade
    assert _grade_from(["منكر الحديث"]) != "غير معروف"            # a cited جرح grades the man


def test_muqaddima_book_title_is_dropped():
    # a محقق source-list item «N - كتاب …» (no network / verdict / signal) is not a narrator
    assert parse_entry(23, "كتاب توجيه النظر الى اصول الاثر للعلامة الشيخ طاهر الجزائري",
                       "كتاب توجيه النظر") is None
