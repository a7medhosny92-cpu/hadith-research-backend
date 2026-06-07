"""Order-aware narrator matching: a reversed name is a different man (roadmap P1.1)."""

from __future__ import annotations

from app.rijal.index import RijalIndex


def _idx():
    return RijalIndex([
        {"name": "جابر بن يزيد الجعفي", "grade": "ضعيف"},
        {"name": "عبد الرحمن بن يزيد بن جابر", "grade": "ثقة"},
        {"name": "أنس بن مالك", "aliases": ["أنس"], "grade": "صحابي"},
    ])


def test_reversed_name_is_not_the_same_person():
    idx = _idx()
    assert idx.lookup("جابر بن يزيد").entry.category == "ضعيف"
    # «يزيد بن جابر» (يزيد then جابر) must NOT resolve to «جابر بن يزيد الجعفي»
    m = idx.lookup("يزيد بن جابر")
    assert m is None or "الجعفي" not in m.entry.name


def test_order_check_does_not_break_normal_lookups():
    idx = _idx()
    assert idx.lookup("أنس").entry.category == "صحابي"            # single token
    assert idx.lookup("عبد الرحمن بن يزيد بن جابر").entry.category == "ثقة"  # exact, in order
