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


# ── the read-only duplicate AUDIT (scripts.audit_duplicates) ──────────────────
def test_audit_duplicates_classifies_the_missed_same_man_clusters():
    """The audit surfaces same-man records the build leaves split, by cause: a كنية-led shadow of a
    full name, an «ابن أبي X» shadow, and a thin-discriminator pair sharing an ident_key — while a
    كنية shared by TWO different men is «ambiguous» (homonymy, not a dup) and distinct men never
    merge. (The measurement instrument for the canonical-base work; it proposes, never edits.)"""
    from scripts.audit_duplicates import audit
    res = audit([
        {"name": "أبو بكر الصديق", "grade": "صحابي"},                         # كنية shadow…
        {"name": "عبد الله بن عثمان أبو بكر الصديق", "grade": "صحابي"},        # …of this full name
        {"name": "ابن أبي مليكة", "grade": "ثقة"},                            # ابن shadow…
        {"name": "عبد الله بن عبيد الله بن أبي مليكة", "grade": "ثقة"},        # …of this
        {"name": "عبد الله بن قيس", "grade": "صحابي"},                        # نقص قرينة (short)…
        {"name": "عبد الله بن قيس أبو موسى الأشعري", "grade": "صحابي"},        # …same ident_key, longer
        {"name": "نصر بن عمران أبو حمزة الضبعي", "grade": "ثقة"},              # a shared كنية across…
        {"name": "محمد بن ميمون أبو حمزة الضبعي", "grade": "صدوق"},           # …two men → ambiguous
        {"name": "أبو حمزة الضبعي", "grade": "ثقة"},                          # the bare shared كنية
        {"name": "سفيان بن عيينة", "grade": "ثقة"},                           # distinct men —
        {"name": "سفيان بن سعيد الثوري", "grade": "ثقة"},                     # must NOT merge
        {"name": "عبد الرحمن بن عوف أحد العشرة المبشرين", "grade": "صحابي"},   # bio leaked into name
    ])
    bc = res["by_class"]
    assert bc["كنية"]["clusters"] == 1 and bc["كنية"]["removable"] == 1
    assert bc["ابن"]["clusters"] == 1
    assert bc["نقص قرينة"]["clusters"] == 1
    assert res["ambiguous"]["كنية"] == 1                 # «أبو حمزة الضبعي» fits two men → not a dup
    assert res["name_pollution"]["count"] == 1           # the bio-tail name
    # the two سفيان never appear in any proposed cluster
    flat = [c["name"] for d in bc.values() for cl in d["examples"] for c in cl]
    assert "سفيان بن عيينة" not in flat and "سفيان بن سعيد الثوري" not in flat


def test_audit_duplicates_precision_guards_reject_homonyms_and_buried_fathers():
    """The audit proposes a merge only when one name is UNAMBIGUOUSLY the same man — the guards that
    keep the measurement honest (they were added after the first real run over-merged): distinct
    same-ism+father namesakes (محمد بن إبراهيم بن الحارث vs … بن دينار) stay apart; a bare form sitting
    under TWO distinct men (أنس الأنصاري vs القشيري) is held; a كنية matching a buried FATHER
    («أبو أمية» inside «… بن أبي أمية») is rejected — while a true prefix-extension and a true own-kunya
    tail still merge."""
    from scripts.audit_duplicates import audit

    # distinct namesakes sharing ism+father + grade must NOT fuse (the over-merge the first run showed)
    r = audit([{"name": "محمد بن إبراهيم بن الحارث التيمي", "grade": "ثقة"},
               {"name": "محمد بن إبراهيم بن دينار المدني", "grade": "ثقة"},
               {"name": "محمد بن إبراهيم بن عثمان العبسي", "grade": "ثقة"}])
    assert r["by_class"]["نقص قرينة"]["clusters"] == 0

    # a bare form under two distinct longer men → ambiguous, held
    r = audit([{"name": "أنس بن مالك", "grade": "صحابي"},
               {"name": "أنس بن مالك بن النضر الأنصاري الخزرجي", "grade": "صحابي"},
               {"name": "أنس بن مالك القشيري الكعبي", "grade": "صحابي"}])
    assert r["by_class"]["نقص قرينة"]["clusters"] == 0

    # a true prefix-extension DOES merge
    r = audit([{"name": "هشام بن عروة", "grade": "ثقة"},
               {"name": "هشام بن عروة بن الزبير الأسدي", "grade": "ثقة"}])
    assert r["by_class"]["نقص قرينة"]["clusters"] == 1

    # a كنية matching a buried FATHER is rejected; a true own-kunya tail merges
    r = audit([{"name": "أبو أمية الأزدي", "grade": "صحابي"},
               {"name": "جنادة بن أبي أمية الأزدي أبو عبد الله الشامي", "grade": "صحابي"}])
    assert r["by_class"]["كنية"]["clusters"] == 0
    r = audit([{"name": "أبو سعيد الخدري", "grade": "صحابي"},
               {"name": "سعد بن مالك بن سنان بن عبيد الأنصاري أبو سعيد الخدري", "grade": "صحابي"}])
    assert r["by_class"]["كنية"]["clusters"] == 1

    # a bare كنية fitting MANY distinct «بنت X» women is held — the ident_key fallback truncates to 3
    # tokens and would collapse them, so the guard compares the full forms (_one_man), not the key
    r = audit([{"name": "أم حبيب", "grade": "صحابي"},
               {"name": "أم حبيب بنت ثمامة", "grade": "صحابي"},
               {"name": "أم حبيب بنت سعيد بن يربوع", "grade": "صحابي"},
               {"name": "أم حبيب بنت العاص", "grade": "صحابي"}])
    assert r["by_class"]["كنية"]["clusters"] == 0 and r["ambiguous"]["كنية"] == 1
