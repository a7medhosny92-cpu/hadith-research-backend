"""Same-man dedup of the رجال gradings (deflating «مشترك» — see app/rijal/dedup.py)."""

from __future__ import annotations

from app.rijal.dedup import collapse_duplicates, same_man


def _names(records):
    return [r["name"] for r in records]


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
