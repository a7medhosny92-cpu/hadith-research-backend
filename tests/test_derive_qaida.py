"""Mining قواعد التمييز from the documented network (scripts.derive_qaida) — the rule «‹ism› عن
‹distinctive شيخ› = ‹that homonym›» is derived, a شيخ SHARED by two namesakes is dropped (لا نختلق)."""

from __future__ import annotations

from collections import Counter

from app.rijal import RijalIndex
from app.rijal.index import _clean_seq
from app.rijal.resolve import network_key
from scripts.derive_qaida import derive_rules


def _df(entries) -> Counter:
    df: Counter = Counter()
    for e in entries:
        for t in set(_clean_seq(e["name"])):
            df[t] += 1
    return df


def test_distinctive_shaykh_becomes_a_qaida_shared_one_is_dropped():
    rows = [
        {"name": "سفيان بن سعيد الثوري", "grade": "ثقة"},
        {"name": "سفيان بن عيينة", "grade": "ثقة"},
        {"name": "سليمان بن مهران الأعمش", "grade": "ثقة"},
        {"name": "عمرو بن دينار المكي", "grade": "ثقة"},
        {"name": "هشام بن عروة", "grade": "ثقة"},          # a شيخ of BOTH سفيانـين → shared, dropped
    ]
    rij = RijalIndex(rows)
    # الثوري ← الأعمش (+ shared هشام); عيينة ← عمرو بن دينار (+ shared هشام)
    teachers = {
        network_key("سفيان بن سعيد الثوري"): {network_key("سليمان بن مهران الأعمش"),
                                              network_key("هشام بن عروة")},
        network_key("سفيان بن عيينة"): {network_key("عمرو بن دينار المكي"),
                                        network_key("هشام بن عروة")},
    }
    rules, floor = derive_rules(rij, teachers, _df(rows), ["سفيان"], max_token_df=50)

    assert "سفيان" in rules
    homs = {h["name"]: h for h in rules["سفيان"]}
    assert set(homs) == {"سفيان بن سعيد الثوري", "سفيان بن عيينة"}
    # the distinctive شيخ's rare token is a marker; the shared هشام never is
    assert "الاعمش" in homs["سفيان بن سعيد الثوري"]["markers"]
    assert "دينار" in homs["سفيان بن عيينة"]["markers"]
    for h in homs.values():
        assert all("هشام" not in m and "عروة" not in m for m in h["markers"])   # shared → never a marker


def test_homonyms_sharing_all_shuyukh_are_the_floor_not_a_rule():
    rows = [
        {"name": "حماد بن زيد", "grade": "ثقة"},
        {"name": "حماد بن سلمة", "grade": "ثقة"},
        {"name": "ثابت البناني", "grade": "ثقة"},
    ]
    rij = RijalIndex(rows)
    # both حمادـان took from ثابت (the ONLY recorded شيخ) → nothing distinctive → ②b floor
    shared = {network_key("ثابت البناني")}
    teachers = {network_key("حماد بن زيد"): set(shared), network_key("حماد بن سلمة"): set(shared)}
    rules, floor = derive_rules(rij, teachers, _df(rows), ["حماد"], max_token_df=50)
    assert "حماد" not in rules and "حماد" in floor
