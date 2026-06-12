"""Tests for named-critic appraisal extraction (app.parsing.appraisals)."""
from __future__ import annotations

from app.parsing.appraisals import extract_appraisals


def test_named_critics_with_verdicts():
    body = ("بَشِيرُ بنُ كَعْبٍ العَدَوِيُّ، رَوَى عَن أبي الدَّرْدَاءِ، رَوَى عَنه قَتَادَةُ. "
            "قَالَ عَلِيُّ بنُ المَدِينِيِّ: ثِقَةٌ ثَبْتٌ. وَقَالَ يَحْيَى بنُ مَعِينٍ: لا بَأْسَ بِهِ. "
            "وَذَكَرَهُ ابنُ حِبَّانَ في الثِّقَاتِ. وَوَثَّقَهُ النَّسَائِيُّ.")
    by = {a["critic"]: a["verdict"] for a in extract_appraisals(body)}
    assert by["ابن المديني"].startswith("ثقة")
    assert by["ابن معين"] == "لا بأس به"
    assert by["ابن حبان"] == "ذكره في الثقات"
    assert by["النسائي"] == "وثّقه"


def test_non_critic_and_ungraded_are_dropped():
    # an isnad narrator (not a critic) and a biographical aside (no grade) are not appraisals
    body = "قَالَ مُحَمَّدُ بنُ عَبدِ اللهِ: حَدَّثَنَا سُفْيَانُ. وَقَالَ أَبُو حَاتِمٍ: كَانَ يَسْكُنُ الكُوفَةَ."
    assert extract_appraisals(body) == []


def test_one_entry_per_critic():
    body = "قَالَ أَبُو حَاتِمٍ: ثِقَةٌ. وَقَالَ أَبُو حَاتِمٍ: لا بَأْسَ بِهِ."
    aps = extract_appraisals(body)
    assert len(aps) == 1 and aps[0]["critic"] == "أبو حاتم الرازي" and aps[0]["verdict"] == "ثقة"


def test_jarh_entry_carries_named_appraisals():
    from app.parsing.jarh_extract import parse_entry
    body = ("بَشِيرُ بنُ كَعْبٍ العَدَوِيُّ، رَوَى عَن أبي الدَّرْدَاءِ، رَوَى عَنه قَتَادَةُ. "
            "قَالَ يَحْيَى بنُ مَعِينٍ: ثِقَةٌ. وَذَكَرَهُ ابنُ حِبَّانَ في الثِّقَاتِ.")
    rec = parse_entry(1541, body)
    crits = {a["critic"] for a in (rec.get("appraisals") or [])}
    assert "ابن معين" in crits and "ابن حبان" in crits


def test_merge_appraisals_attaches_by_name_and_carries_through():
    from app.rijal.index import RijalIndex
    from scripts.build_rijal import merge_appraisals
    records = [{"name": "بشير بن كعب العدوي", "grade": "ثقة", "source": "تقريب التهذيب (رقم 8609)"}]
    prose = [{"name": "بشير بن كعب العدوي",
              "appraisals": [{"critic": "ابن معين", "verdict": "ثقة"}]}]
    out, n = merge_appraisals(records, prose)
    assert n == 1
    card = RijalIndex(out).lookup("بشير بن كعب العدوي").to_dict()
    assert card["appraisals"][0]["critic"] == "ابن معين"
