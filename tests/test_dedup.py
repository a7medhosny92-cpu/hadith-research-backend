"""Same-man dedup of the رجال gradings (deflating «مشترك» — see app/rijal/dedup.py)."""

from __future__ import annotations

import sqlite3

from app.rijal.dedup import CorpusCompany, collapse_duplicates, ident_key, same_man


def _names(records):
    return [r["name"] for r in records]


def _graph(path, nodes, links):
    """A tiny narrators.db: ``nodes`` = [(id, name, freq)], ``links`` = [(teacher_id, student_id)]."""
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE narrator (id INTEGER PRIMARY KEY, norm TEXT, name TEXT, freq INTEGER)")
    con.execute("CREATE TABLE link (teacher INTEGER, student INTEGER, weight INTEGER)")
    con.executemany("INSERT INTO narrator VALUES (?, '', ?, ?)", nodes)
    con.executemany("INSERT INTO link VALUES (?, ?, 1)", links)
    con.commit()
    con.close()
    return CorpusCompany(path)


def test_shared_nisba_duplicate_is_one_man():
    # هشام بن عمار الدمشقي written two ways (تقريب laqab الخطيب · الكاشف kunya أبو الوليد): the
    # tails differ so the source-merge can't unify them, but the shared nisba السلمي/الدمشقي
    # (with compatible grades) makes them one man.
    a = {"name": "هشام بن عمار بن نصير السلمي الدمشقي الخطيب", "grade": "صدوق", "source": "تقريب التهذيب"}
    b = {"name": "هشام بن عمار أبو الوليد السلمي الدمشقي المقرئ", "grade": "ثقة",
         "kunya": "أبو الوليد", "source": "الكاشف"}
    assert same_man(a, b)
    kept, removed = collapse_duplicates([a, b])
    assert removed == 1 and len(kept) == 1
    assert {o["source"] for o in kept[0]["opinions"]} == {"تقريب التهذيب", "الكاشف"}  # both views kept
    assert kept[0]["name"].count(" ") >= a["name"].count(" ")                         # fullest name survives


def test_identical_kunya_confirms_same_man_without_a_nisba():
    a = {"name": "الليث بن سعد أبو الحارث الإمام", "kunya": "أبو الحارث", "grade": "ثقة", "source": "تقريب"}
    b = {"name": "الليث بن سعد بن عبد الرحمن الفهمي أبو الحارث المصري", "kunya": "أبو الحارث",
         "grade": "ثقة", "source": "الكاشف"}
    assert same_man(a, b)
    kept, removed = collapse_duplicates([a, b])
    assert removed == 1 and len(kept) == 1


def test_generation_marker_keeps_grandfather_and_grandson_apart():
    # نصر بن علي الجهضمي الكبير ≠ his حفيد — a genuine homonym that must stay «مشترك».
    a = {"name": "نصر بن علي الجهضمي الكبير", "grade": "ثقة", "source": "تقريب"}
    b = {"name": "نصر بن علي بن نصر الجهضمي حفيد الذي قبله", "grade": "ثقة", "source": "الكاشف"}
    assert not same_man(a, b)
    kept, removed = collapse_duplicates([a, b])
    assert removed == 0 and len(kept) == 2


def test_disjoint_nisba_keeps_two_men_apart():
    a = {"name": "محمد بن جعفر الموصلي", "grade": "ثقة"}
    b = {"name": "محمد بن جعفر الدورقي البغدادي", "grade": "صدوق"}
    assert not same_man(a, b)
    assert collapse_duplicates([a, b])[1] == 0


def test_strong_grade_conflict_blocks_the_merge():
    # same name + nisba but graded oppositely (ثقة vs متروك): we can't be sure it's one man, so
    # we refuse — it stays «مشترك» and the chain is held, never graded on a guess.
    a = {"name": "سعيد بن بشير الأزدي", "grade": "ثقة", "source": "تقريب"}
    b = {"name": "سعيد بن بشير الأزدي", "grade": "متروك", "source": "الكاشف"}
    assert not same_man(a, b)
    assert collapse_duplicates([a, b])[1] == 0


def test_grandfather_conflict_keeps_two_men_apart():
    # same ident_key (أحمد بن عبد الله) but a conflicting grandfather (بن يونس ≠ بن محمد) — two
    # different men the bare name confuses. The lineage check, not the nisba, must keep them apart.
    a = {"name": "أحمد بن عبد الله بن يونس بن عبد الله اليربوعي", "grade": "ثقة", "source": "تقريب"}
    b = {"name": "أحمد بن عبد الله بن محمد بن عبد الله الوكيل", "grade": "صدوق", "source": "الكاشف"}
    assert ident_key(a["name"]) == ident_key(b["name"])     # they collide on ism+father…
    assert not same_man(a, b)                                # …but the grandfather tells them apart
    assert collapse_duplicates([a, b])[1] == 0


def test_compound_father_is_not_truncated_to_one_token():
    # «عبد الله» must not collapse to «عبد» — «أحمد بن عبد الله» and «أحمد بن عبد الواحد» are
    # different men and must not even group together.
    a = {"name": "أحمد بن عبد الله بن يونس", "grade": "ثقة"}
    b = {"name": "أحمد بن عبد الواحد بن واقد التميمي", "grade": "ثقة"}
    assert ident_key(a["name"]) != ident_key(b["name"])
    assert not same_man(a, b)


def test_collapse_leaves_distinct_names_and_unrelated_entries_untouched():
    records = [
        {"name": "يزيد بن هارون بن زاذان السلمي أبو خالد الواسطي", "kunya": "أبو خالد", "grade": "ثقة", "source": "تقريب"},
        {"name": "يزيد بن هارون أبو خالد السلمي الواسطي", "kunya": "أبو خالد", "grade": "ثقة", "source": "الكاشف"},
        {"name": "مالك بن أنس الأصبحي", "grade": "ثقة", "source": "تقريب"},     # unrelated — untouched
    ]
    kept, removed = collapse_duplicates(records)
    assert removed == 1
    assert "مالك بن أنس الأصبحي" in _names(kept)
    assert sum(1 for n in _names(kept) if n.startswith("يزيد بن هارون")) == 1


def test_corpus_company_vetoes_a_homonym_the_name_would_fuse(tmp_path):
    # «أحمد بن عيسى المصري التنيسي» and «… المصري التستري» share the nisba المصري, so the name
    # proposes a merge — but the corpus cites them with disjoint company → two men → vetoed.
    comp = _graph(
        tmp_path / "g.db",
        nodes=[(1, "أحمد بن عيسى التنيسي", 30), (2, "أحمد بن عيسى التستري", 20),
               (3, "شيخ أول", 5), (4, "شيخ ثان", 5), (5, "شيخ ثالث", 5), (6, "شيخ رابع", 5)],
        links=[(3, 1), (4, 1), (5, 2), (6, 2)],          # node 1 ↔ {3,4}; node 2 ↔ {5,6}: disjoint
    )
    a = {"name": "أحمد بن عيسى المصري التنيسي", "grade": "ثقة"}
    b = {"name": "أحمد بن عيسى المصري التستري", "grade": "صدوق"}
    assert same_man(a, b)                                 # the name alone would merge them
    assert comp.vetoes(a["name"], b["name"])              # the corpus contradicts it
    assert collapse_duplicates([a, b], company=comp)[1] == 0       # mix: vetoed, not merged
    assert collapse_duplicates([a, b])[1] == 1                     # name-only: merged (the false fuse)


def test_corpus_company_confirms_one_man(tmp_path):
    comp = _graph(
        tmp_path / "g.db",
        nodes=[(1, "هشام بن عمار", 100), (2, "الوليد بن مسلم", 9), (3, "سفيان بن عيينة", 9)],
        links=[(2, 1), (3, 1)],
    )
    a = {"name": "هشام بن عمار الدمشقي الخطيب", "grade": "صدوق"}
    b = {"name": "هشام بن عمار الدمشقي المقرئ", "grade": "ثقة"}
    assert comp.confirms(a["name"], b["name"]) and not comp.vetoes(a["name"], b["name"])
    assert collapse_duplicates([a, b], company=comp)[1] == 1       # one node → merged


def test_corpus_company_absent_man_is_trusted_to_the_name(tmp_path):
    # neither man is in the graph → the mix does NOT veto (trusts the name); the strict policy does.
    comp = _graph(tmp_path / "g.db", nodes=[(1, "مالك بن أنس", 50)], links=[])
    a = {"name": "يزيد بن هارون السلمي الواسطي", "kunya": "أبو خالد", "grade": "ثقة"}
    b = {"name": "يزيد بن هارون بن زاذان السلمي الواسطي", "kunya": "أبو خالد", "grade": "ثقة"}
    assert not comp.vetoes(a["name"], b["name"])
    assert collapse_duplicates([a, b], company=comp)[1] == 1                       # mix: merged
    assert collapse_duplicates([a, b], company=comp, require_confirm=True)[1] == 0  # strict: not
