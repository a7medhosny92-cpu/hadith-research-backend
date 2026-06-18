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


def test_anna_report_with_no_qal_is_recovered():
    # «عن نافع أنّ ابن عمر كان …» / «عن رسول الله ﷺ: أنّه توضّأ …» — a mawqūf/marfūʿ report
    # introduced by «أنّ» with NO «قال» (the dominant empty-matn / V audit case). The matn must
    # start at «أنّ», and the chain before it stay isnad.
    iz, matn, conf = split_isnad_matn(
        "حدثنا فلان عن مالك عن نافع، أنَّ عبد الله بن عمر كان إذا أحرم من مكة لم يطف بالبيت")
    assert conf == "anna"
    assert matn.startswith("أنَّ عبد الله بن عمر") and "كان إذا أحرم" in matn
    assert "نافع" in iz and "نافع" not in matn
    _, m2, c2 = split_isnad_matn(
        "حدثنا فلان عن عمر، عن رسول الله ﷺ: أنَّه توضأ عام تبوك واحدة واحدة")
    assert c2 == "anna" and m2.startswith("أنَّه توضأ") and "عام تبوك" in m2


def test_anna_skips_a_sub_narrator_link_and_starts_at_the_report():
    # «… أنّ فلانًا أخبره: أنّه فعل …» — the FIRST «أنّ» opens another isnad link («أخبره»), so the
    # matn must begin at the SECOND «أنّ» (the report), not swallow the sub-narrator.
    iz, matn, _ = split_isnad_matn(
        "حدثنا فلان عن حميد، أنَّ عبد الرحمن بن عبد القاري أخبره: أنَّه طاف بالبيت مع عمر فصلى ركعتين")
    assert matn.startswith("أنَّه طاف بالبيت") and "أخبره" not in matn
    assert "عبد الرحمن بن عبد القاري أخبره" in iz


def test_authority_introduced_matn_quote_without_qal_is_recovered():
    # «عن النبيّ ﷺ: "إذا استأذنت امرأة أحدكم فلا يمنعها"» — a quoted matn introduced by the terminal
    # authority with no «قال». The matn is the quote; the chain stays isnad.
    iz, matn, conf = split_isnad_matn(
        'حدثنا فلان عن الزهري عن سالم عن أبيه، عن النبيِّ ﷺ: "إذا استأذنت امرأة أحدكم فلا يمنعها"')
    assert conf == "authority"
    assert "إذا استأذنت امرأة أحدكم فلا يمنعها" in matn
    assert "الزهري" in iz and "الزهري" not in matn


def test_chain_comparison_backreference_stays_matn_less():
    # al-Ḥākim's chain-comparison «… عن النبيّ ﷺ؛ في حديث القبر. وأما حديث زائدة» and a «بمعنى فلان»
    # back-reference carry NO independent matn — they must stay empty (not be force-recovered).
    assert split_isnad_matn(
        "حدثنا فلان عن الأعمش عن المنهال عن البراء، عن النبي ﷺ؛ في حديث القبر . وأما حديث زائدة"
    )[1] == ""
    assert split_isnad_matn(
        "حدثنا فلان عن حماد عن يونس وحميد، عن الحسن، عن النبي ﷺ، بمعنى قتادة")[1] == ""


def test_normal_qal_split_is_unaffected_by_the_anna_fallback():
    # the «أنّ»/authority fallbacks are LATE (empty-only) — a normal «قال:» matn must still split
    # exactly as before even when an «أنّ» appears earlier in the chain.
    _, matn, conf = split_isnad_matn(
        "حدثنا فلان أن أبا هريرة أخبره أن رسول الله ﷺ قال: من غشنا فليس منا")
    assert conf in ("phrase", "quote")
    assert "من غشنا فليس منا" in matn and "أخبره" not in matn


def test_dual_qala_does_not_split_leaving_the_route_in_the_matn():
    # «حدّثنا A وB قالا: حدّثنا [route] … أنّ النبيّ ﷺ matn» — the bare «قال» must NOT match the «قال»
    # inside the dual «قالا» (the leftover «ا:» then blocked the route re-peel, dumping the whole
    # secondary chain into the matn → the dominant «إسناد في المتن» / I case in Sunan Ibn Māja).
    isnad, matn, _ = split_isnad_matn(
        "حدثنا أبو بكر وعلي قالا: حدثنا عبد العزيز، عن زيد، عن عطاء، عن ابن عباس "
        "أن رسول الله ﷺ مضمض واستنشق")
    assert matn.startswith("رسول الله ﷺ") and "مضمض واستنشق" in matn
    assert "عبد العزيز" in isnad and "حدثنا" not in matn      # the route stayed in the isnad
    # the plural «قالوا:» as a genuine matn-introducer must still split
    _, m2, _ = split_isnad_matn("حدثنا فلان عن أصحابه قالوا: نهى رسول الله ﷺ عن بيع الغرر")
    assert m2 == "نهى رسول الله ﷺ عن بيع الغرر"


def test_scene_opening_stays_in_the_matn_bayna_idh():
    # «… قال: بينما رسول الله ﷺ … إذ قال لأصحابه: "متن"» — the «بينما … إذ» scene is the matn, not the
    # isnad. The inner «قال لأصحابه» must NOT become the boundary (البخاري 6649).
    isnad, matn, _ = split_isnad_matn(
        "حدثني عبد الله بن مسعود ﷺ قال: بينما رسول الله ﷺ مضيف ظهره إلى قبة من أدم، "
        'إذ قال لأصحابه: "أترضون أن تكونوا ربع أهل الجنة؟"')
    assert matn.startswith("بينما رسول الله") and "أترضون" in matn
    assert "بينما" not in isnad


def test_temporal_lamma_opening_stays_in_the_matn():
    # «… عن النبي ﷺ قال: لما مات إبراهيم قال: إن له مرضعا في الجنة» — «لمّا [حدث] قال» is the matn
    # opening; the last-«قال» split must not drop it into the isnad (البخاري 3261).
    isnad, matn, _ = split_isnad_matn(
        "حدثنا شعبة، قال: سمعت البراء ﷺ، عن النبي ﷺ قال: لما مات إبراهيم قال: إن له مرضعا في الجنة")
    assert matn.startswith("لما مات إبراهيم") and "إن له مرضعا" in matn
    # a «لمّا» that is the PROPHET's own words (after «قال رسول الله ﷺ:») must NOT trigger the scene
    # split — «لما» stays in the matn and is never pushed into the isnad.
    isnad2, m2, _ = split_isnad_matn(
        "حدثنا فلان، عن أبيه، قال: قال رسول الله ﷺ: لما خلق الله الخلق كتب كتابا")
    assert "لما خلق الله" in m2 and "كتب كتابا" in m2 and "لما" not in isnad2


def test_marfu_attribution_is_not_taken_for_a_story():
    # «… عن أبي المتوكل، أنّ أبا سعيد الخدري ﷺ قال: قال رسول الله ﷺ: "المتن"» — «أنّ [صحابيّ] قال: قال
    # رسولُ الله» is a marfūʿ ATTRIBUTION, not a scene: the matn is the Prophet's words, the صحابيّ link
    # stays in the isnad (البخاري 6543).
    isnad, matn, _ = split_isnad_matn(
        "حدثنا سعيد، عن قتادة، عن أبي المتوكل الناجي، أن أبا سعيد الخدري ﷺ قال: "
        'قال رسول الله ﷺ: "يخلص المؤمنون من النار فيحبسون على قنطرة"')
    assert matn.startswith("يخلص المؤمنون")
    assert "أبا سعيد" in isnad and "أبا سعيد" not in matn      # the صحابيّ stayed in the chain


def test_vocalised_dual_qala_seam_is_not_a_matn_boundary():
    # «حدّثنا A وB قَالَا: حدّثنا [route] … أنّ النبيّ ﷺ …» — fully VOCALISED, as the corpus is. «قَالَا» =
    # قَال + fatha + alif, so the old «(?![ء-ي])» end-anchor passed (next char is a haraka) and split
    # inside «قَالَا», stranding the orphan «ـَا:» + the whole secondary route in the matn — the dominant
    # «إسناد في المتن» case in the Sunan. The anchor must step over the diacritic.
    isnad, matn, _ = split_isnad_matn(
        "حَدَّثَنَا أَبُو بَكْرٍ وَعَلِيٌّ قَالَا: حَدَّثَنَا وَكِيعٌ، عَنْ سُفْيَانَ، عَنْ أَبِيهِ "
        "أَنَّ النَّبِيَّ ﷺ كَانَ يَتَوَضَّأُ لِكُلِّ صَلَاةٍ")
    assert matn.strip().startswith("النَّبِيَّ") and "كَانَ يَتَوَضَّأُ" in matn
    assert "وَكِيعٌ" in isnad and "وَكِيعٌ" not in matn          # the route stayed in the isnad


def test_taliq_co_narrator_route_at_matn_head_is_re_peeled():
    # «حدّثنا [شيخ]، قال الليثُ: حدّثني [route] … عن رسول الله ﷺ: <body>» — al-Bukhārī's «وقال الليث»
    # muʿallaq: the split consumed «قال», stranding «الليث: حدّثني [route]» in the matn. The «[راوٍ]:
    # حدّثني» head is re-peeled back into the isnad and the body recovered (audit RULE 2, ~45 cases).
    isnad, matn, _ = split_isnad_matn(
        "حَدَّثَنَا يَحْيَى بْنُ بُكَيْرٍ، قَالَ اللَّيْثُ: حَدَّثَنِي جَعْفَرُ بْنُ رَبِيعَةَ، "
        "عَنْ عَبْدِ الرَّحْمَنِ، عَنْ أَبِي هُرَيْرَةَ، عَنْ رَسُولِ اللَّهِ ﷺ: ذَكَرَ رَجُلًا مِنْ بَنِي إِسْرَائِيلَ")
    assert matn.startswith("ذَكَرَ رَجُلًا") and "حَدَّثَنِي" not in matn   # the route went back to the isnad
    assert "اللَّيْثُ" in isnad and "جَعْفَرُ" in isnad


def test_prohibition_verb_before_the_authority_stays_in_the_matn():
    # «… عن ابن عمر، نَهَى رسولُ الله ﷺ عن بيع الثمار …» — the terminal-authority split takes only «عن
    # بيع الثمار», stranding «نَهَى» (the prohibition = the matn) in the isnad. The verb must be kept
    # (audit RULE 3, ~58 cases — incl. the «عن الغلام شاتان» class).
    isnad, matn, _ = split_isnad_matn(
        "حَدَّثَنَا قُتَيْبَةُ، عَنْ نَافِعٍ، عَنِ ابْنِ عُمَرَ، نَهَى رَسُولُ اللَّهِ ﷺ عَنْ بَيْعِ الثِّمَارِ حَتَّى يَبْدُوَ صَلَاحُهَا")
    assert matn.startswith("نَهَى رَسُولُ اللَّهِ") and "بَيْعِ الثِّمَارِ" in matn
    assert "ابْنِ عُمَرَ" in isnad and "نَهَى" not in isnad
    # a NORMAL «عن النبيّ ﷺ: "<body>"» (no prohibition verb before) is unchanged
    _, m2, _ = split_isnad_matn(
        'حَدَّثَنَا فلان عن الزهري، عن النبيِّ ﷺ: "إذا استأذنت امرأة أحدكم فلا يمنعها"')
    assert "إذا استأذنت امرأة" in m2 and "نهى" not in m2
