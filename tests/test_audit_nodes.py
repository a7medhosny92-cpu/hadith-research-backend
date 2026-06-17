"""Tests for the isnad-parsing-bug detector (scripts.audit_nodes.junk_in_node)."""

from __future__ import annotations

import pytest

from scripts.audit_nodes import junk_in_node


@pytest.mark.parametrize("name", [
    "محمد بن عبد الله",
    "علي بن أبي طالب",
    "سمعان بن مالك",        # «سمع»-prefixed NAME — must not trip the verb regex
    "قرة بن خالد",          # «قر…» NAME — not the verb «قرأ»
    "أبو هريرة",
    "عبد الرحمن بن عوف",
    "رسول الله صلى الله عليه وسلم",   # the Prophet's eulogy is not junk
])
def test_clean_nodes_are_not_flagged(name):
    assert junk_in_node(name) == []


@pytest.mark.parametrize("name, token, cls", [
    ("الزهري أخبره", "اخبره", "verb"),        # the object-pronoun verb leak
    ("حدثه أبو سلمة", "حدثه", "verb"),
    ("قرأت على مالك", "قرات", "verb"),         # the قراءة/عرض leak
    ("عمر بن الخطاب قال", "قال", "say"),
    ("عائشة كان", "كان", "action"),
    ("ابن عمر أنه", "انه", "anna"),
    ("فلان مثله", "مثله", "backref"),
])
def test_corrupted_nodes_are_classified(name, token, cls):
    assert (token, cls) in junk_in_node(name)


@pytest.mark.parametrize("name, token, cls", [
    ("عبد", "عبد", "truncation"),                 # a bare «servant-of» — truncation of «عبد الله/الرحمن»
    ("أبو", "ابو", "truncation"),
    ("اللفظ له", "اللفظ", "editorial"),            # «واللفظ له» — an editorial interjection, not a name
    ("الشيخ أبو بكر بن إسحاق", "الشيخ", "editorial"),  # a leading title
    ("عبد الله بن المبارك وبهذا", "وبهذا", "backref"),  # the «وبهذا الإسناد» back-ref leak
])
def test_truncation_editorial_and_backref_nodes_are_flagged(name, token, cls):
    assert (token, cls) in junk_in_node(name)
