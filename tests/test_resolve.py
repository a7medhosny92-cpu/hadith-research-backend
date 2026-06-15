"""Joint anchored تمييز المهمل — app.rijal.resolve."""

from __future__ import annotations

from app.rijal.resolve import DocumentedNetwork, network_key, resolve_chain

_k = network_key
_THAWRI = "سفيان بن سعيد الثوري"
_UYAYNA = "سفيان بن عيينة"
_AMASH = "سليمان بن مهران الأعمش"


def test_resolves_ambiguous_via_documented_shaykh():
    """«سفيان» (الثوري vs عيينة) sits above الأعمش. الأعمش's documented تلاميذ include الثوري but
    NOT عيينة → the chain itself decides سفيان = الثوري, no guessing."""
    cands = [["وكيع بن الجراح"], [_THAWRI, _UYAYNA], [_AMASH], ["إبراهيم النخعي"]]
    anchors = ["وكيع بن الجراح", None, _AMASH, "إبراهيم النخعي"]
    net = DocumentedNetwork(students={_k(_AMASH): {_k(_THAWRI)}})   # الأعمش taught الثوري, not عيينة
    assert resolve_chain(cands, anchors, net)[1] == _THAWRI


def test_resolves_via_documented_tilmidh_too():
    """The mirror: the link ABOVE (my تلميذ) constrains me. وكيع is a documented تلميذ of الثوري only
    (not of عيينة) → «سفيان» below him resolves to الثوري."""
    cands = [["وكيع بن الجراح"], [_THAWRI, _UYAYNA], [_AMASH]]
    anchors = ["وكيع بن الجراح", None, _AMASH]
    net = DocumentedNetwork(students={_k(_THAWRI): {_k("وكيع بن الجراح")}})
    assert resolve_chain(cands, anchors, net)[1] == _THAWRI


def test_propagates_certainty_generation_by_generation():
    """Anchored at the صحابي, certainty spreads UP: علقمة resolves from ابن مسعود, then إبراهيم
    from علقمة, then الأعمش from إبراهيم — each newly-fixed link anchors the next."""
    cands = [["الأعمش الكوفي", _AMASH],          # ambiguous until إبراهيم is fixed
             ["إبراهيم بن يزيد", "إبراهيم النخعي"],  # ambiguous until علقمة is fixed
             ["علقمة بن قيس", "علقمة بن وقاص"],      # ambiguous until ابن مسعود anchors it
             ["عبد الله بن مسعود"]]                  # the صحابي anchor
    anchors = [None, None, None, "عبد الله بن مسعود"]
    net = DocumentedNetwork(students={
        _k("عبد الله بن مسعود"): {_k("علقمة بن قيس")},
        _k("علقمة بن قيس"): {_k("إبراهيم النخعي")},
        _k("إبراهيم النخعي"): {_k(_AMASH)},
    })
    resolved = resolve_chain(cands, anchors, net)
    assert resolved == [_AMASH, "إبراهيم النخعي", "علقمة بن قيس", "عبد الله بن مسعود"]


def test_holds_when_company_is_itself_ambiguous():
    """The honest floor (the user's point): a bare «سفيان» whose only neighbour «عبد الله» is
    itself unresolved and carries no documented relation → nothing decides it → held (None),
    never guessed."""
    cands = [["عبد الله"], [_THAWRI, _UYAYNA], ["عبد الله"]]
    anchors = [None, None, None]
    assert resolve_chain(cands, anchors, DocumentedNetwork())[1] is None
    # even WITH a network, if no candidate is documented in the (resolved) relation → still held
    net = DocumentedNetwork(students={_k(_AMASH): {_k(_THAWRI)}})  # irrelevant to this chain
    assert resolve_chain(cands, anchors, net)[1] is None


def test_conflicting_evidence_holds_not_guesses():
    """If BOTH homonyms are documented in the relation (the شيخ taught both سفيان's), the link is
    genuinely undecided by company → held, not guessed."""
    cands = [[_THAWRI, _UYAYNA], [_AMASH]]
    anchors = [None, _AMASH]
    net = DocumentedNetwork(students={_k(_AMASH): {_k(_THAWRI), _k(_UYAYNA)}})
    assert resolve_chain(cands, anchors, net)[0] is None


def test_documented_students_keeps_the_direction():
    """The builder resolves each man and his quoted شيوخ/تلاميذ to a رجال canonical name and records
    the شيخ→تلميذ direction from BOTH a man's تلاميذ list and his شيوخ list."""
    from app.rijal.index import RijalIndex
    from app.rijal.tahdhib import documented_students
    rijal = RijalIndex([
        {"name": _THAWRI, "grade": "ثقة"}, {"name": _AMASH, "grade": "ثقة"},
        {"name": "وكيع بن الجراح", "grade": "ثقة"},
    ])
    records = [
        {"name": _AMASH, "talamidh": ["سفيان الثوري"], "shuyukh": []},   # الأعمش taught الثوري
        {"name": "وكيع بن الجراح", "shuyukh": ["سفيان الثوري"], "talamidh": []},  # وكيع heard from الثوري
    ]
    students = documented_students(records, rijal)
    assert _k(_THAWRI) in students[_k(_AMASH)]            # from the تلاميذ side
    assert _k("وكيع بن الجراح") in students[_k(_THAWRI)]  # from the شيوخ side (mirror)
    # and it actually drives the resolver: bare «سفيان» above الأعمش → الثوري
    net = DocumentedNetwork(students=students)
    assert resolve_chain([[_THAWRI, _UYAYNA], [_AMASH]], [None, _AMASH], net)[0] == _THAWRI


def test_network_save_load_round_trip(tmp_path):
    from app.rijal.resolve import load_network, save_network
    students = {_k(_AMASH): {_k(_THAWRI), _k("وكيع بن الجراح")}}
    path = tmp_path / "net.json"
    save_network(students, path)
    net = load_network(path)
    assert net.is_student_of(_THAWRI, _AMASH) and net.is_teacher_of(_AMASH, _THAWRI)
    assert not net.is_student_of(_UYAYNA, _AMASH)
    assert not load_network(tmp_path / "absent.json")     # missing file → empty, falsy
