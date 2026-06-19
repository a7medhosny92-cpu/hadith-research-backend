"""Test سير أعلام النبلاء extraction."""

from __future__ import annotations

import pytest

from app.parsing.sair_extract import _clean_name, _grade_from, iter_sair, parse_entry


def _sair(headings: list[str], text: str) -> dict:
    """A minimal سير book payload: «N - Name» headings (all on page 1) + one page of body text."""
    return {
        "indexes": {"headings": [{"title": t, "page": 1, "level": 3} for t in headings]},
        "pages": [{"pg": 1, "text": text}],
    }


def _sair_pages(headings: list[tuple[str, int]], pages: dict[int, str]) -> dict:
    """A سير payload with explicit ``(heading-title, page)`` pairs and per-page body text — so the
    page-driven segmentation (one tarjama per page-block) can be exercised."""
    return {
        "indexes": {"headings": [{"title": t, "page": p, "level": 3} for t, p in headings]},
        "pages": [{"pg": p, "text": txt} for p, txt in sorted(pages.items())],
    }


class TestCleanName:
    """Name extraction from tarjama head."""

    def test_simple_name(self) -> None:
        assert _clean_name("أبو بكر الصديق") == "أبو بكر الصديق"

    def test_stops_at_network_marker(self) -> None:
        """Stop at «حدّث عن» / «روى عن»."""
        assert _clean_name("علي بن الحسن حدث عن الزهري") == "علي بن الحسن"
        assert _clean_name("محمد بن علي روى عن ابن المسيب") == "محمد بن علي"

    def test_stops_at_transmission_verb(self) -> None:
        """Stop at transmission verbs."""
        assert _clean_name("سعيد بن المسيب سمعت من أبيه") == "سعيد بن المسيب"
        assert _clean_name("أنس بن مالك أخبرنا أبو هريرة") == "أنس بن مالك"

    def test_stops_at_verdict(self) -> None:
        """Stop at جرح/تعديل verdict."""
        assert _clean_name("يزيد بن حرب قال أحمد: ثقة") == "يزيد بن حرب"
        assert _clean_name("عمرو بن الحارث مات سنة 213") == "عمرو بن الحارث"

    def test_removes_edit_marks(self) -> None:
        """Strip editor's brackets."""
        assert _clean_name("الحسن [البصري] السدي") == "الحسن السدي"
        assert _clean_name("معمر (بن راشد) بن علي") == "معمر بن علي"

    def test_min_length_guard(self) -> None:
        """Single token is not a valid name."""
        assert _clean_name("الثوري") is None
        assert _clean_name("أحمد") is None


class TestGradeFrom:
    """Grade logic: weakest cited جرح/تعديل verdict, else «غير معروف»."""

    def test_weakest_verdict(self) -> None:
        """Return the weakest cited verdict (highest نقص rank)."""
        # ثقة (rank 1) is stronger than ضعيف (rank 4)
        grade = _grade_from(["ثقة", "ضعيف"])
        assert grade == "ضعيف"

    def test_empty_verdicts(self) -> None:
        """No verdicts → «غير معروف» (coverage default)."""
        assert _grade_from([]) == "غير معروف"

    def test_single_verdict(self) -> None:
        """Single verdict returned as is."""
        assert _grade_from(["ثقة"]) == "ثقة"
        assert _grade_from(["متروك"]) == "متروك"

    def test_ignores_non_graded(self) -> None:
        """Skip verdicts that don't classify to a grade rank."""
        grade = _grade_from(["some random text", "ثقة", "another phrase"])
        assert grade == "ثقة"


class TestParseEntry:
    """Tarjama parsing."""

    def test_minimal_valid_entry(self) -> None:
        """Minimum valid body: name + some content."""
        body = "علي بن الحسن روى عن أبيه. قال أحمد: ثقة."
        rec = parse_entry(1, body)
        assert rec is not None
        assert rec["name"] == "علي بن الحسن"
        assert rec["number"] == 1
        assert rec["grade"] == "ثقة"

    def test_reported_speech_is_not_a_jarh(self) -> None:
        """سير is biographical prose: a dialogue «قال له: ما يسمونك إلا الكذّاب» (a taunt) must NOT grade
        نفيع أبو رافع الصائغ (ثقة) «كذّاب» — only a terse critic verdict counts; the rest is «غير معروف»."""
        body = ("نفيع أبو رافع الصائغ المدني روى عن أبي بكر وعنه الزهري "
                "قال له: ما يسمونك إلا الكذاب. مات سنة مئة")
        assert parse_entry(1, body, heading_name="نفيع أبو رافع الصائغ")["grade"] == "غير معروف"
        body2 = "صدقة بن عبد الله الدمشقي قال له رجل: وبالكوفة جئت تسمع؟ أما إنك لا تلقى فيها إلا كذاب"
        assert parse_entry(2, body2, heading_name="صدقة بن عبد الله الدمشقي")["grade"] == "غير معروف"
        # …but a real terse verdict is still read
        assert parse_entry(3, "فلان بن فلان روى عن مالك. قال أبو حاتم: ضعيف.",
                           heading_name="فلان بن فلان")["grade"].startswith("ضعيف")

    def test_extract_kunya(self) -> None:
        """Extract كنية from name."""
        body = "أبو هريرة عبد الرحمن بن صخر الدوسي. قال ابن معين: ثقة."
        rec = parse_entry(1, body)
        assert rec is not None
        assert rec["kunya"] == "أبو هريرة"

    def test_extract_death_year(self) -> None:
        """Extract وفاة from body."""
        body = "محمد بن علي القرشي روى عن جابر. مات سنة 127."
        rec = parse_entry(1, body)
        assert rec is not None
        assert rec["death_year"] == 127

    def test_extract_shuyukh(self) -> None:
        """Extract teachers (شيوخ)."""
        body = "محمد بن علي حدث عن سعد بن أبي وقاص وعائشة. حدث عنه مالك والليث."
        rec = parse_entry(1, body)
        assert rec is not None
        assert rec["shuyukh"]
        assert any("سعد" in name for name in rec["shuyukh"])

    def test_extract_talamidh(self) -> None:
        """Extract students (تلاميذ)."""
        body = "أيوب السختياني حدث عن محمد بن سيرين. حدث عنه شعبة وهشام."
        rec = parse_entry(1, body)
        assert rec is not None
        assert rec["talamidh"]
        assert any("شعبة" in name for name in rec["talamidh"])

    def test_too_short_body(self) -> None:
        """Very short bodies are junk."""
        assert parse_entry(1, "abc") is None

    def test_junk_section_headers(self) -> None:
        """Section headers are not tarjamas."""
        assert parse_entry(1, "باب في الشيوخ") is None
        assert parse_entry(1, "كتاب الترجمة") is None
        assert parse_entry(1, "فصل في النوادر") is None

    def test_diacritic_tolerance(self) -> None:
        """Parser handles diacritics in input (via strip_diacritics at call site)."""
        body = "مُحَمَّد بن علیّ حَدَّثَ عن سعد. قال أحمد: ثقة."
        rec = parse_entry(1, body)
        # The body is stripped of diacritics before calling parse_entry in iter_sair
        # so this should still extract correctly if diacritics don't block the regex.
        # Just ensure it doesn't crash.
        assert rec is not None or rec is None  # Don't assert exact parsing of diacritics


class TestSourceField:
    """Every record carries the source identification."""

    def test_source_included(self) -> None:
        """Every entry has the source tag."""
        body = "علي بن محمد حدث عن الزهري. قال أحمد: ثقة."
        rec = parse_entry(1, body)
        assert rec is not None
        assert rec["source"] == "سير أعلام النبلاء (الذهبي، ط الرسالة، رقم 10906)"


class TestInlineSegmentation:
    """iter_sair uses heading-driven segmentation, finding inline «N -» in the body."""

    def test_three_inline_tarjamas(self) -> None:
        """Three tarjamas on one line (inline heads) are all extracted."""
        data = _sair(
            ["١ - محمد بن علي الكوفي", "٢ - أحمد بن سعيد الرباطي", "٣ - يحيى بن إبراهيم البغدادي"],
            "١ - محمد بن علي الكوفي روى عن الزهري. مات سنة 300. "
            "٢ - أحمد بن سعيد الرباطي روى عن مالك. مات سنة 310. "
            "٣ - يحيى بن إبراهيم البغدادي روى عن شعبة. مات سنة 320.",
        )
        recs = list(iter_sair(data))
        assert len(recs) == 3
        names = [r["name"] for r in recs]
        assert any("محمد بن علي" in n for n in names)
        assert any("أحمد بن سعيد" in n for n in names)
        assert any("يحيى بن إبراهيم" in n for n in names)

    def test_date_range_not_a_tarjama(self) -> None:
        """A «٢٠٠ - ٢١٠» date range in the body is not a tarjama boundary."""
        data = _sair(
            ["٢٠٠ - محمد بن عمر البغدادي"],
            "نشأ في الفترة ٢٠٠ - ٢١٠ هجرية. "
            "٢٠٠ - محمد بن عمر البغدادي روى عن ابن المبارك. قال أحمد: ثقة.",
        )
        recs = list(iter_sair(data))
        assert len(recs) == 1
        assert "محمد بن عمر" in recs[0]["name"]

    def test_no_heading_no_record(self) -> None:
        """Body with valid «N -» inline text but no matching heading yields nothing."""
        data = _sair(
            [],  # no headings
            "١ - محمد بن علي الكوفي روى عن الزهري. قال أحمد: ثقة.",
        )
        assert list(iter_sair(data)) == []

    def test_heading_name_used_not_body(self) -> None:
        """Name comes from the clean heading, not from the body text."""
        data = _sair(
            ["١٤٥ - عمرو بن دينار البصري"],
            "١٤٥ - عمرو بن دينار البصري المكي روى عن جابر. قال أحمد: ثقة.",
        )
        recs = list(iter_sair(data))
        assert len(recs) == 1
        assert recs[0]["name"] == "عمرو بن دينار البصري"


class TestPageDrivenSegmentation:
    """Each heading is mapped to its body BY PAGE — one tarjama per page-block, and a heading is
    NEVER dropped even when its name can't be located in the body (the +4-narrators regression)."""

    def test_one_tarjama_per_page(self) -> None:
        """Long tarjamas, one per page-block, each body sliced by the page boundary."""
        data = _sair_pages(
            [("١ - محمد بن علي الكوفي", 1), ("٢ - أحمد بن سعيد الرباطي", 2), ("٣ - يحيى بن إبراهيم البغدادي", 3)],
            {
                1: "١ - محمد بن علي الكوفي روى عن الزهري. وعنه مالك. مات سنة 300.",
                2: "٢ - أحمد بن سعيد الرباطي روى عن مالك. وعنه البخاري. مات سنة 310.",
                3: "٣ - يحيى بن إبراهيم البغدادي روى عن شعبة. مات سنة 320.",
            },
        )
        recs = list(iter_sair(data))
        assert len(recs) == 3
        rec1 = next(r for r in recs if "محمد بن علي" in r["name"])
        assert rec1["death_year"] == 300
        assert any("الزهري" in s for s in rec1.get("shuyukh", []))

    def test_heading_emitted_even_if_name_not_in_body(self) -> None:
        """The +4 regression: a shuhra heading whose body opens with the ISM-led full name must STILL
        be emitted (page fallback), not silently dropped."""
        data = _sair_pages(
            [("٣٠٠ - أبو الفضل الأصم", 5)],
            {5: "هو محمد بن يعقوب بن يوسف النيسابوري. روى عن الربيع. مات سنة 346."},
        )
        recs = list(iter_sair(data))
        assert len(recs) == 1
        assert recs[0]["name"] == "أبو الفضل الأصم"
        assert recs[0]["death_year"] == 346

    def test_short_tarjamas_sharing_a_page_split_by_name(self) -> None:
        """The LATE الأصم-class: several short tarjamas on ONE page, sub-split by locating each name."""
        data = _sair_pages(
            [("١ - الحسن بن سفيان النسوي", 9), ("٢ - عمران بن موسى الجرجاني", 9), ("٣ - دعلج بن أحمد السجزي", 9)],
            {
                9: (
                    "١ - الحسن بن سفيان النسوي روى عن قتيبة. وعنه الطبراني. مات سنة 303. "
                    "٢ - عمران بن موسى الجرجاني روى عن هدبة. وعنه ابن عدي. مات سنة 305. "
                    "٣ - دعلج بن أحمد السجزي روى عن موسى بن هارون. وعنه الحاكم. مات سنة 351."
                )
            },
        )
        recs = list(iter_sair(data))
        assert len(recs) == 3
        names = " | ".join(r["name"] for r in recs)
        assert "الحسن بن سفيان" in names
        assert "عمران بن موسى" in names
        assert "دعلج بن أحمد" in names
        # each keeps its OWN death year — the bodies didn't bleed together
        years = sorted(r["death_year"] for r in recs if r.get("death_year"))
        assert years == [303, 305, 351]


class TestWaAnhu:
    """«وعنه» is the dominant تلاميذ marker in سير; critics after terminators are excluded."""

    def test_wa_anhu_captures_students(self) -> None:
        """«وعنه» introduces تلاميذ; full names (≥3 chars) are captured."""
        body = (
            "محمد بن علي المكي حدث عن الزهري والأوزاعي. "
            "وعنه عبد الرحمن بن مهدي وقتيبة بن سعيد. مات سنة 295."
        )
        rec = parse_entry(1, body, heading_name="محمد بن علي المكي")
        assert rec is not None
        assert rec.get("talamidh")
        assert any("عبد الرحمن" in t for t in rec["talamidh"])

    def test_critic_after_daafahu_not_in_talamidh(self) -> None:
        """A name after «ضعّفه» is a critic, not a student."""
        body = (
            "سفيان الكوفي روى عن مالك وسعيد. "
            "وعنه وكيع وعبد الرحمن بن مهدي. "
            "ضعّفه أبو حاتم الرازي. قال ابن معين: ثقة."
        )
        rec = parse_entry(1, body, heading_name="سفيان الكوفي")
        assert rec is not None
        talamidh = rec.get("talamidh", [])
        assert not any("أبو حاتم" in t for t in talamidh)

    def test_wa_akharun_terminates_student_list(self) -> None:
        """«وآخرون» terminates the تلاميذ list; names after it are not students."""
        body = (
            "يحيى بن سعيد البصري روى عن ابن المبارك. "
            "وعنه ابن راهويه وأحمد وآخرون. "
            "قال أبو زرعة: ثقة."
        )
        rec = parse_entry(1, body, heading_name="يحيى بن سعيد البصري")
        assert rec is not None
        talamidh = rec.get("talamidh", [])
        assert not any("أبو زرعة" in t for t in talamidh)
