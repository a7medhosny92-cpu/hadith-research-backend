"""قواعد تمييز المهمل — the curated شيخ-conditioned disambiguations."""

from __future__ import annotations

from app.rijal.qaida import resolve_qaida


def test_sufyan_by_shaykh():
    assert resolve_qaida("سفيان", "الأعمش") == "سفيان بن سعيد الثوري"
    assert resolve_qaida("سفيان", "منصور بن المعتمر") == "سفيان بن سعيد الثوري"
    assert resolve_qaida("سفيان", "عمرو بن دينار") == "سفيان بن عيينة"
    assert resolve_qaida("سفيان", "الزهري") == "سفيان بن عيينة"
    assert resolve_qaida("سُفْيَانُ", "الأَعْمَشِ") == "سفيان بن سعيد الثوري"   # vocalised


def test_hammad_and_hisham():
    assert resolve_qaida("حماد", "أيوب") == "حماد بن زيد"
    assert resolve_qaida("حماد", "ثابت البناني") == "حماد بن سلمة"
    assert resolve_qaida("هشام", "أبيه") == "هشام بن عروة"
    assert resolve_qaida("هشام", "قتادة") == "هشام الدستوائي"
    assert resolve_qaida("هشام", "ابن سيرين") == "هشام بن حسان"


def test_held_when_not_a_discriminator_or_not_bare():
    assert resolve_qaida("سفيان", "شعبة") is None             # شعبة doesn't discriminate
    assert resolve_qaida("سفيان بن عيينة", "الأعمش") is None  # already specified, not a bare homonym
    assert resolve_qaida("مالك", "نافع") is None              # no qā'ida for this name


def test_yahya_sulayman_khalid():
    assert resolve_qaida("يحيى بن سعيد", "شعبة") == "يحيى بن سعيد القطان"
    assert resolve_qaida("يحيى بن سعيد", "عبيد الله بن عمر") == "يحيى بن سعيد القطان"
    assert resolve_qaida("يحيى بن سعيد", "سعيد بن المسيب") == "يحيى بن سعيد الأنصاري"
    assert resolve_qaida("سليمان", "أبي وائل") == "سليمان بن مهران الأعمش"
    assert resolve_qaida("سليمان", "أبي عثمان النهدي") == "سليمان بن طرخان التيمي"
    assert resolve_qaida("خالد", "أبي قلابة") == "خالد بن مهران الحذاء"
    assert resolve_qaida("خالد", "يونس بن عبيد") == "خالد بن عبد الله الطحان"
    assert resolve_qaida("يحيى بن سعيد", "رجل") is None        # no discriminator → held


def test_jarir_aswad_ismail():
    assert resolve_qaida("جرير", "منصور") == "جرير بن عبد الحميد"
    assert resolve_qaida("جرير", "أيوب") == "جرير بن حازم"
    assert resolve_qaida("الأسود", "علقمة") == "الأسود بن يزيد"
    assert resolve_qaida("الأسود", "شعبة") == "الأسود بن عامر"
    assert resolve_qaida("إسماعيل", "قيس بن أبي حازم") == "إسماعيل بن أبي خالد"
    assert resolve_qaida("إسماعيل", "أيوب") is None          # the ابن علية side is left held (shared شيوخ)


def test_zayd_ibn_waqid_is_the_dimashqi_by_his_shami_shaykh():
    # زيد بن واقد القرشي الدمشقي (ثقة) vs الستّي البصري (متروك): the Dimashqi narrates from his Shami
    # شيوخ (بسر بن عبيد الله، مكحول، حرام بن حكيم، مغيث بن سُمَيّ، خالد بن عبد الله بن حسين).
    for sh in ("بسر بن عبيد الله", "مكحول", "مغيث بن سمي", "حرام بن حكيم", "خالد بن عبد الله بن حسين"):
        assert resolve_qaida("زيد بن واقد", sh) == "زيد بن واقد القرشي الدمشقي"
    assert resolve_qaida("زيد بن واقد", "أيوب السختياني") is None   # a non-Shami شيخ → held, never guessed


def test_yunus_and_hajjaj_by_shaykh():
    # يونس: الأيليُّ عن الزهري · العبديُّ عن الحسن/ابن سيرين · السبيعيُّ عن أبيه أبي إسحاق
    assert resolve_qaida("يونس", "الزهري") == "يونس بن يزيد الأيلي"
    assert resolve_qaida("يونس", "ابن شهاب الزهري") == "يونس بن يزيد الأيلي"
    assert resolve_qaida("يونس", "الحسن البصري") == "يونس بن عبيد بن دينار العبدي"
    assert resolve_qaida("يونس", "محمد بن سيرين") == "يونس بن عبيد بن دينار العبدي"
    assert resolve_qaida("يونس", "أبي إسحاق السبيعي") == "يونس بن أبي إسحاق السبيعي"
    assert resolve_qaida("يونس", "عكرمة") is None                  # not a discriminator → held
    # حجاج بن محمد المصيصيُّ الأعور عن ابن جريج/شعبة (the famous «حجاج»); ابن أرطاة (عن عطاء) left held
    assert resolve_qaida("حجاج", "ابن جريج") == "حجاج بن محمد المصيصي"
    assert resolve_qaida("حجاج", "شعبة") == "حجاج بن محمد المصيصي"
    assert resolve_qaida("حجاج", "عطاء بن أبي رباح") is None
