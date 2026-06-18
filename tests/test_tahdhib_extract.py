"""Tests for the تهذيب الكمال (al-Mizzī) prose رجال extractor.

The real book (id 3722) is gitignored/ephemeral, so these exercise the pure parser on crafted —
but realistically vocalised — tarjama bodies. See ``docs/TAHDHIB.md`` for the book study.
"""

from __future__ import annotations

from app.parsing.tahdhib_extract import _muqaddima_skip, parse_entry


def test_parse_entry_reads_books_name_kunya_network_and_verdict():
    body = (
        "خ م ق: عُثْمَانُ بْنُ مُحَمَّدٍ العَبْسِيُّ، أَبُو الحَسَنِ بْنُ أَبِي شَيْبَةَ الكُوفِيُّ. "
        "رَوَى عَن: أَحْمَدَ بْنِ إِسْحَاقَ (م)، وجَرِيرِ بْنِ عَبْدِ الحَمِيدِ. "
        "رَوَى عَنه: البُخَارِيُّ، ومُسْلِمٌ، وابْنُ مَاجَهْ. "
        "قَالَ ابْنُ مَعِينٍ: ثِقَةٌ."
    )
    r = parse_entry(3857, body)
    assert r["books"] == ["خ", "م", "ق"]                          # the rumūz (Six-Books symbols)
    assert r["name"].startswith("عُثْمَانُ بْنُ مُحَمَّدٍ")        # name stops before «رَوَى عَن:»
    assert r["kunya"].startswith("أَبُو الحَسَن")
    assert len(r["shuyukh"]) == 2 and any("أَحْمَد" in s for s in r["shuyukh"])
    assert r["talamidh"] == ["البُخَارِيُّ", "مُسْلِمٌ", "ابْنُ مَاجَهْ"]    # his real students
    assert any("ثِقَة" in v for v in r["verdicts"])               # diacritised grade word matched


def test_parse_entry_handles_the_abbreviated_an_colon_form():
    # minor narrators use «عَن:» / «وعَنه:» (not the full «رَوَى عَن:») — both must open the blocks
    # and the bare chain word «عَنْ فلان» (no colon) must NOT be mistaken for the opener.
    body = "د س: بِشْرُ بْنُ سَحِيمٍ الغِفَارِيُّ، لَهُ صُحْبَةٌ. عَن: النَّبِيِّ ﷺ. وعَنه: عَلِيُّ بْنُ أَبِي طَالِبٍ."
    r = parse_entry(688, body)
    assert r["name"].startswith("بِشْرُ بْنُ سَحِيمٍ")             # the bio did not swallow the name
    assert r["shuyukh"] and r["talamidh"]


def test_parse_entry_rejects_a_too_short_body():
    assert parse_entry(1, "خ م") is None


def test_parse_entry_skips_the_author_and_late_biographees():
    # al-Mizzī himself (the AUTHOR, ت742) and «أبا الحجاج المزي» (ت734) leaked in as رجال entries
    # (with panegyric «الإمام … محدث الشام» mis-read as a grade). A «X الدين» honorific OR a death
    # past ~400h marks a non-narrator — no Six-Books transmitter is either.
    assert parse_entry(1, "جمال الدين أبو الحجاج يوسف المزي الإمام محدث الشام. مات سنة ٧٤٢.") is None
    assert parse_entry(1, "أبو الحجاج المزي الحافظ. مات سنة ٧٣٤.") is None
    # a genuine third-century narrator with a normal death year is still kept
    r = parse_entry(1, "خ م: محمد بن بشار بندار. روى عن: غندر. مات سنة ٢٥٢.")
    assert r is not None and r["name"].startswith("محمد بن بشار")


def test_muqaddima_skip_lands_on_the_dense_rumuz_run():
    # the محقق's ~200-page intro carries non-rumūz numbered points; the dictionary proper is a
    # dense run of rumūz-bearing entries. The skip jumps over the intro to that run.
    assert _muqaddima_skip([True] * 20) == 0                      # all narrators → no skip
    assert 25 <= _muqaddima_skip([False] * 30 + [True] * 20) <= 30   # 30 intro items → skip them
    assert _muqaddima_skip([False] * 5) == 0                      # too short to decide → start at 0


def test_tahdhib_company_disambiguates_a_homonym():
    # the payoff: al-Mizzī's شيوخ/تلاميذ resolve an ambiguous bare name from its chain company.
    from app.rijal import RijalIndex
    from app.rijal.canon import Canonicalizer
    from app.rijal.index import _clean_tokens
    from app.rijal.tahdhib import tahdhib_associations

    rij = RijalIndex([                                            # two «حماد» homonyms…
        {"name": "حماد بن زيد", "grade": "ثقة"},
        {"name": "حماد بن سلمة", "grade": "ثقة"},
        {"name": "أيوب السختياني", "grade": "ثقة"},
        {"name": "ثابت البناني", "grade": "ثقة"},
    ])
    records = [                                                   # …each with a distinct شيخ in تهذيب
        {"name": "حماد بن زيد", "shuyukh": ["أيوب السختياني"], "talamidh": []},
        {"name": "حماد بن سلمة", "shuyukh": ["ثابت البناني"], "talamidh": []},
    ]
    assoc = tahdhib_associations(records, rij)
    assert "حماد بن زيد" in assoc and "حماد بن سلمة" in assoc     # keyed by رجال canonical name
    canon = Canonicalizer(rij, associations=assoc)
    # «حماد عن أيوب» is ابن زيد; «حماد عن ثابت» is ابن سلمة — decided by the تهذيب company alone.
    assert canon.canonical("حماد", context=frozenset(_clean_tokens("أيوب السختياني"))) == "حماد بن زيد"
    assert canon.canonical("حماد", context=frozenset(_clean_tokens("ثابت البناني"))) == "حماد بن سلمة"


def test_tahdhib_associations_skip_an_ambiguous_or_unknown_narrator():
    from app.rijal import RijalIndex
    from app.rijal.tahdhib import tahdhib_associations

    rij = RijalIndex([{"name": "مالك بن أنس", "grade": "ثقة"}])
    # «فلان» is unknown to the authority → no association keyed onto a name we can't pin.
    assert tahdhib_associations([{"name": "فلان المجهول", "shuyukh": ["نافع"]}], rij) == {}
