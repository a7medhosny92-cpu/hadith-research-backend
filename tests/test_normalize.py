from app.parsing.normalize import normalize_for_search, strip_diacritics


def test_strip_diacritics_keeps_letters():
    # removes tashkeel but preserves hamza-on-alef (letter identity intact)
    assert strip_diacritics("إِنَّمَا الْأَعْمَالُ") == "إنما الأعمال"


def test_normalize_folds_alef_variants():
    assert normalize_for_search("إِنَّمَا الْأَعْمَالُ") == "انما الاعمال"


def test_query_matches_vocalised_source():
    # the whole point: a bare user query matches a fully-vocalised matn
    source = "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ"
    query = "انما الاعمال بالنيات"
    assert normalize_for_search(source) == normalize_for_search(query)


def test_ta_marbuta_and_alef_maqsura_folded():
    assert normalize_for_search("صَلَاةٌ") == "صلاه"
    assert normalize_for_search("مُوسَى") == "موسي"


def test_tatweel_removed():
    assert normalize_for_search("الحـــمد") == "الحمد"


def test_accusative_tanwin_alif_dropped():
    """A name in the accusative («جابرًا», «رأيت مجاهدًا») normalises to its base — the tanwin alif
    is dropped before the harakāt are stripped, so it matches «جابر»/«مجاهد»."""
    from app.parsing.normalize import strip_diacritics, normalize_for_search
    assert strip_diacritics("جابرًا") == "جابر"
    assert strip_diacritics("مجاهداً") == "مجاهد"
    assert normalize_for_search("مجاهدًا") == normalize_for_search("مجاهد")


def test_compound_name_variable_spacing_folds():
    """«معديكرب» is one name (المقدام بن معديكرب الكندي, صحابي) but the internal space lands
    differently in the chain vs the base — all spellings fold to one token so they match."""
    from app.parsing.normalize import normalize_for_search
    canon = normalize_for_search("المقدام بن معديكرب الكندي")
    assert normalize_for_search("المقدام بن معد يكرب الكندي") == canon
    assert normalize_for_search("المقدام بن معدي كرب الكندي") == canon
    assert normalize_for_search("كربلاء") != canon            # an unrelated word is untouched
