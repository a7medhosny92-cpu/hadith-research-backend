"""The matn must not swallow an editorial/takhrij tail between quotes (audit PARSE-1)."""

from __future__ import annotations

from app.parsing.isnad_matn import split_isnad_matn


def test_editorial_tail_after_the_matn_is_dropped():
    _, matn, conf = split_isnad_matn(
        'حدثنا فلان يقول: "إنما الأعمال بالنيات" قال أبو عبد الله: ويقال "نية" بمعنى آخر'
    )
    assert conf == "quote"
    assert matn == "إنما الأعمال بالنيات"


def test_takhrij_reference_tail_is_dropped():
    _, matn, _ = split_isnad_matn('حدثنا فلان قال: "متن الحديث" تحفة الأشراف 123')
    assert matn == "متن الحديث"


def test_dialogue_spans_are_kept_whole():
    _, matn, _ = split_isnad_matn(
        'حدثنا فلان قال: «جاء رجل» فقال له النبي: «اذهب» فقال: «نعم»'
    )
    assert "جاء رجل" in matn and "اذهب" in matn and "نعم" in matn


def test_phrase_and_none_fallbacks_unchanged():
    assert split_isnad_matn("حدثنا فلان عن أنس قال: إنما الأعمال")[2] == "phrase"
    assert split_isnad_matn("حدثنا فلان عن أنس")[2] == "none"


def test_narrative_matn_keeps_the_whole_story_not_just_the_first_quote():
    # «… عن أبيه: أنّ رجلًا أتى النبيّ ﷺ … قال: فقال: "ادع تلك الشجرة" …» — a STORY whose first
    # quote sits mid-narrative. The matn must be the whole story (question + answer + sequel),
    # not just «ادع تلك الشجرة», and the chain must stay in the isnad. (al-Mustadrak 7514.)
    isnad, matn, conf = split_isnad_matn(
        "حدثنا فلان، عن عبد الله ابن بريدة، عن أبيه: أنَّ رجلًا أتى النبيَّ ﷺ فقال: "
        'علِّمني شيئًا، قال: فقال: "ادع تلك الشجرة"، فدعا بها فجاءت حتى سلَّمت عليه، '
        'ثم قال لها: "ارجعي" فرجعت'
    )
    assert conf == "quote"
    assert matn.startswith("أنَّ رجلًا أتى النبيَّ")
    assert "ادع تلك الشجرة" in matn and "ارجعي" in matn   # the whole narrative is kept
    assert "ابن بريدة" in isnad and "ادع" not in isnad     # the chain stays isnad


def test_nested_chain_anna_is_not_pulled_into_the_matn():
    # «أنّه سمع فلانًا يقول: سمعت فلانًا … قال: "…"» is a nested CHAIN (سمع/سمعت links), not a
    # story — the matn is only the final saying; the transmission «أنّ» stays in the isnad.
    isnad, matn, _ = split_isnad_matn(
        "حدثنا فلان، عن محمد، أنه سمع علقمة يقول: سمعت عمر يقول: "
        'سمعت رسول الله ﷺ يقول: "إنما الأعمال بالنيات"'
    )
    assert matn == "إنما الأعمال بالنيات"
    assert "سمع علقمة" in isnad


def test_grade_tail_is_trimmed_from_a_phrase_matn():
    # the al-Ḥākim grade «هذا حديث صحيح الإسناد ولم يخرّجاه» the book prints after the matn
    # must never show as matn.
    _, matn, _ = split_isnad_matn(
        "حدثنا فلان قال: قال رسول الله ﷺ: خيرُكم خيرُكم للنساء. هذا حديث صحيح الإسناد ولم يخرجاه"
    )
    assert "خيرُكم خيرُكم للنساء" in matn
    assert "هذا حديث" not in matn and "يخرجاه" not in matn


def test_wa_fi_albab_crossreference_is_trimmed():
    _, matn, _ = split_isnad_matn(
        "حدثنا فلان قال: قال رسول الله ﷺ: لا ضرر ولا ضرار. وفي الباب عن أبي هريرة"
    )
    assert "لا ضرر ولا ضرار" in matn and "وفي الباب" not in matn


def test_takhrij_cross_reference_tail_is_trimmed_from_the_matn():
    # the «رواه/أخرجه فلان» takhrīj note the source appends after the body (al-Bukhārī/al-Ḥākim
    # cross-references — the dominant «حكم/تخريج في المتن» / G audit case) must not show as matn.
    _, m1, _ = split_isnad_matn(
        "حدثنا فلان قال: قال رسول الله ﷺ: صلوا كما رأيتموني أصلي رواه البخاري")
    assert "صلوا كما رأيتموني أصلي" in m1 and "رواه" not in m1 and "البخاري" not in m1
    _, m2, _ = split_isnad_matn(
        "حدثنا فلان قال: قال رسول الله ﷺ: من حفر بئرا وقع فيه. أخرجه مسلم وأحمد")
    assert "من حفر بئرا وقع فيه" in m2 and "أخرجه" not in m2 and "مسلم" not in m2


def test_takhrij_trim_does_not_eat_a_matn_verb():
    # «أخرجه الله» / «رواه عنه» are real body, NOT a takhrīj note — the trim must keep them
    # (guarded: it fires only on a sentence-opening cross-ref or «رواه/أخرجه + collection»).
    _, m1, _ = split_isnad_matn(
        "حدثنا فلان قال: قال رسول الله ﷺ: من قال لا إله إلا الله أخرجه الله من النار")
    assert "أخرجه الله من النار" in m1
    _, m2, _ = split_isnad_matn(
        "حدثنا فلان قال: قال رسول الله ﷺ: الحديث الذي رواه عنه أصحابه حق")
    assert "رواه عنه أصحابه" in m2


def test_tahwil_secondary_chain_leaked_into_the_matn_is_re_split():
    # «حدثنا [شيخ] قال: حدثنا [route] … قال <matn>» — the first split cuts after the شيخ's «قال:»,
    # leaving the real route + body at the matn's head; the re-split folds the route back into the
    # isnad and recovers the body (the dominant «إسناد في المتن» / I audit case = تحويل ح).
    from app.parsing.isnad_matn import split_isnad_matn
    text = "حدثنا أبو بكر قال: حدثنا أبو الزبير عن جابر أن رسول الله ﷺ قال إنما الماء من الماء"
    isnad, matn, conf = split_isnad_matn(text)
    assert matn == "إنما الماء من الماء"
    assert "حدثنا أبو الزبير" in isnad and "حدثنا أبو الزبير" not in matn
