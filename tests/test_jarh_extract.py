"""Tests for the الجرح والتعديل (Ibn Abī Ḥātim) prose رجال extractor.

The real book (id 2170) is gitignored/ephemeral, so these exercise the pure parser on crafted —
but realistically shaped — tarjama bodies (numbered head, colon-less «روى عن/روى عنه» network)."""

from __future__ import annotations

from app.parsing.jarh_extract import parse_entry


def test_parses_colonless_network_and_multicritic_verdicts():
    body = (
        "بشير بن كعب بصري أبو أيوب العدوي روى عن أبي الدرداء وأبي ذر "
        "روى عنه طلق بن حبيب والعلاء بن زياد. سمعت أبي يقول: بشير بن كعب ثقة. "
        "حدثنا عبد الرحمن قال قال علي بن المديني: بشير بن كعب معروف."
    )
    r = parse_entry(1541, body)
    assert r["name"].startswith("بشير بن كعب")                  # name stops before «روى عن»
    assert r["kunya"].startswith("أبو أيوب")
    assert any("الدرداء" in s for s in r["shuyukh"])            # شيوخ from «روى عن …»
    assert any("طلق" in t for t in r["talamidh"])               # تلاميذ from «روى عنه …»
    assert "أبي الدرداء" not in r["talamidh"]                   # the two blocks don't bleed
    assert any("ثقة" in v for v in r["verdicts"])               # a graded appraisal is kept


def test_grave_verdict_is_captured():
    body = ("زياد بن المنذر أبو الجارود الثقفي روى عن عطية روى عنه مروان الفزاري. "
            "قال يحيى بن معين: أبو الجارود كذاب ليس بثقة.")
    r = parse_entry(2462, body)
    assert any("كذاب" in v for v in r["verdicts"])


def test_a_chapter_heading_is_not_a_narrator():
    assert parse_entry(1, "باب تسمية من روى عنه العلم ممن اسمه بلال") is None
    assert parse_entry(2, "كوفي") is None                       # too short / no real name
