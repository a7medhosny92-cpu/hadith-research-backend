"""Coverage audit — how much of the chain narrators the رجال base grades (scripts.audit_coverage)."""

from __future__ import annotations

from app.rijal import RijalIndex
from scripts.audit_coverage import audit


def test_coverage_classifies_identified_ambiguous_and_uncovered():
    """Each chain narrator node is classified against the base: a unique match = identified, a name with
    ≥2 homonyms = ambiguous (covered but «مشترك»), no match = uncovered (the gap). Counted by distinct
    node AND by chain-position frequency."""
    records = [
        {"name": "مالك بن أنس الأصبحي", "grade": "ثقة"},
        {"name": "محمد بن جعفر البزاز", "grade": "صدوق"},        # two distinct محمد بن جعفر …
        {"name": "محمد بن جعفر الهذلي غندر", "grade": "ثقة"},     # … so a bare citation is ambiguous
    ]
    rijal = RijalIndex(records)
    nodes = [
        ("مالك بن أنس", 100),               # → identified (one man)
        ("محمد بن جعفر", 80),               # → ambiguous (البزاز / الهذلي)
        ("فلان الفلاني المجهول لا وجود له", 5),  # → uncovered (not in the base)
    ]
    res = audit(rijal, nodes)
    assert res["by_node"] == {"identified": 1, "ambiguous": 1, "uncovered": 1}
    assert res["by_pos"]["identified"] == 100        # freq-weighted (chain positions)
    assert res["by_pos"]["uncovered"] == 5
    assert res["nodes"] == 3 and res["positions"] == 185
    assert res["uncovered_top"][0][0] == "فلان الفلاني المجهول لا وجود له"
