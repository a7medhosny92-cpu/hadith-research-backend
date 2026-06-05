from app.ingestion.catalog import ALL_COMMENTARY_IDS, COMMENTARIES, CORE_COLLECTIONS, Catalog

SAMPLE = {
    "cats": {
        "6": {"id": 6, "name": "كتب السنة", "books": [1284, 1727]},
        "7": {"id": 7, "name": "شروح الحديث", "books": [8540, 1673]},
    },
    "books": {
        "1284": {"id": 1284, "name": "صحيح البخاري", "author_id": 71, "cat_id": 6,
                 "has_pdf": True, "size": 100, "page_count": 4719},
        "1727": {"id": 1727, "name": "صحيح مسلم", "author_id": 90, "cat_id": 6,
                 "has_pdf": True, "size": 200, "page_count": 7495},
        "8540": {"id": 8540, "name": "شرح سنن أبي داود للعيني", "author_id": 71,
                 "cat_id": 7, "has_pdf": True, "size": 50, "page_count": 3279},
        "1673": {"id": 1673, "name": "فتح الباري بشرح البخاري", "author_id": 99,
                 "cat_id": 7, "has_pdf": True, "size": 80, "page_count": 7996},
    },
    "authors": {"71": {"id": 71, "name": "البخاري", "death": 256}},
    "version": 3,
}


def test_from_raw_parses_records():
    cat = Catalog.from_raw(SAMPLE)
    assert len(cat.books) == 4
    assert cat.books[1284].page_count == 4719
    assert cat.cats[6].name == "كتب السنة"
    assert cat.authors[71].death == 256


def test_books_in_categories():
    cat = Catalog.from_raw(SAMPLE)
    cat6 = cat.books_in_categories([6])
    assert {b.id for b in cat6} == {1284, 1727}


def test_select_priority_first_then_categories_without_dupes():
    cat = Catalog.from_raw(SAMPLE)
    selected = cat.select(cat_ids=[6, 7], priority=True)
    ids = [b.id for b in selected]
    # core collections present in the catalog come first, no duplicates
    assert ids[0] == 1284 and ids[1] == 1727
    assert len(ids) == len(set(ids)) == 4


def test_select_explicit_book_ids():
    cat = Catalog.from_raw(SAMPLE)
    assert [b.id for b in cat.select(book_ids=[8540, 999])] == [8540]


def test_total_pages():
    cat = Catalog.from_raw(SAMPLE)
    assert cat.total_pages(cat.books_in_categories([6])) == 4719 + 7495


def test_core_collections_are_known_ids():
    assert 1284 in CORE_COLLECTIONS and CORE_COLLECTIONS[1284] == "صحيح البخاري"


def test_commentaries_map_and_dedupe():
    # Fath al-Bari is registered as a commentary on Sahih al-Bukhari
    assert 1673 in COMMENTARIES[1284]
    # the flat list is de-duplicated
    assert len(ALL_COMMENTARY_IDS) == len(set(ALL_COMMENTARY_IDS))


def test_commentaries_for_resolves_against_catalog():
    cat = Catalog.from_raw(SAMPLE)
    sharh = cat.commentaries_for(1284)
    assert [b.id for b in sharh] == [1673]


def test_select_with_commentaries_appends_sharh():
    cat = Catalog.from_raw(SAMPLE)
    selected = cat.select(book_ids=[1284], with_commentaries=False)
    assert [b.id for b in selected] == [1284]
    # priority seeds Bukhari, then its commentary (فتح الباري) is appended
    selected = cat.select(cat_ids=[6], with_commentaries=True)
    ids = [b.id for b in selected]
    assert 1284 in ids and 1673 in ids and ids.index(1673) > ids.index(1284)
