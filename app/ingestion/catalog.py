"""Parse and query the turath.io catalog (``data-v3.json``).

The catalog is a single JSON document::

    {
      "cats":    {"6": {"id": 6, "name": "كتب السنة", "books": [21, 27, ...]}, ...},
      "books":   {"1284": {"id": 1284, "name": "...", "author_id": 71,
                            "cat_id": 6, "has_pdf": true, "size": 214912,
                            "page_count": 4719}, ...},
      "authors": {"71": {"id": 71, "name": "...", "death": 855, "books": [...]}, ...},
      "version": ..., "date": ...
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# Curated default seed: the canonical hadith collections, by real turath book id.
# Ordered by importance so a prioritised crawl yields a useful system fast.
# (ids verified against the live catalog.)
CORE_COLLECTIONS: dict[int, str] = {
    1284: "صحيح البخاري",
    1727: "صحيح مسلم",
    1726: "سنن أبي داود",
    1435: "جامع الترمذي",
    1339: "سنن النسائي (المجتبى)",
    1198: "سنن ابن ماجه",
    1699: "موطأ مالك",
    25794: "مسند أحمد",
    1446: "صحيح ابن خزيمة",
    1729: "صحيح ابن حبان (الإحسان)",
    1424: "المستدرك على الصحيحين",
    9771: "سنن الدارقطني",
}

# Major scholarly commentaries (شروح الحديث — turath cat 7) keyed by the base
# collection they explain. These carry the explanations of the ʿulamāʾ that we want
# to surface alongside each hadith (with attribution to the commentator). ids verified.
COMMENTARIES: dict[int, list[int]] = {
    1284: [1673, 5756, 21716, 137],  # البخاري: فتح الباري (ابن حجر)، عمدة القاري، إرشاد الساري، فتح الباري (ابن رجب)
    1727: [1711, 148870],            # مسلم: شرح النووي (المنهاج)، البحر المحيط الثجاج
    1435: [21662, 1337],             # الترمذي: تحفة الأحوذي، حاشية السندي
    1726: [5760, 37052, 20764],      # أبو داود: عون المعبود، شرح العباد، المنهل العذب المورود
    1339: [522],                     # النسائي: حاشية السندي
    1198: [9810],                    # ابن ماجه: حاشية السندي
    1699: [6684],                    # الموطأ: المنتقى شرح الموطإ (الباجي)
    25794: [124910, 14299],          # مسند أحمد: الفتح الرباني (الساعاتي)، عقود الزبرجد (السيوطي)
    1446: [37017],                   # ابن خزيمة: شرح صحيح ابن خزيمة (الراجحي)
    1729: [37009, 641],              # ابن حبان: شرح (الراجحي)، التعليقات الحسان (الألباني)
    1424: [96551],                   # المستدرك: مختصر تلخيص الذهبي (حكم الذهبي على الأحاديث)
}

#: Flat, de-duplicated list of every curated commentary book id.
ALL_COMMENTARY_IDS: tuple[int, ...] = tuple(
    dict.fromkeys(sid for ids in COMMENTARIES.values() for sid in ids)
)

# Terse رجال books — one graded entry per narrator — that the rijal extractor
# (app.parsing.rijal_extract) can parse into gradings for /verify-isnad. Order matters:
# the FIRST is the authority and the rest only fill gaps / add missing narrators
# (see scripts.build_rijal.merge_source). تقريب التهذيب (Ibn Ḥajar) covers essentially
# every narrator of the Six Books with a one-word verdict; الكاشف (al-Dhahabī) is a
# second terse source for the same men. ids verified against the catalog.
RIJAL_SOURCES: dict[int, str] = {
    8609: "تقريب التهذيب",
    2171: "الكاشف",
}

# Verbose (prose) رجال / صحابة biographies. They are NOT hadith, and their flowing prose does NOT
# reduce to one terse verdict, so they are *excluded from the hadith parse* (otherwise their pages
# pollute the hadith index — each tarjama would surface as a bogus matn-less «hadith») but are
# deliberately NOT in RIJAL_SOURCES — build_rijal's terse extractor would mangle them. Dedicated
# prose extractors (per book) are future work; until then they are simply kept out of the corpus.
RIJAL_PROSE_BOOKS: dict[int, str] = {
    3722: "تهذيب الكمال",
    2170: "الجرح والتعديل لابن أبي حاتم",   # early, independent, multi-critic — covers beyond the Six Books
    1278: "تهذيب التهذيب (ط دبي)",
    1293: "تهذيب التهذيب (ط الرسالة)",
    # ── Companion (صحابة) dictionaries + broad ثقات/ميزان coverage (downloaded 2026-06-11 to fill
    #    «مجهول»; extractors pending — see ROADMAP/CLAUDE.md). MUST be skipped here so the parse
    #    doesn't read their biographies as matn-less hadith (the +26k «empty matn» regression).
    9767: "الإصابة في تمييز الصحابة (ابن حجر)",
    1110: "أسد الغابة (ابن الأثير)",
    12288: "الاستيعاب (ابن عبد البر)",
    10490: "معرفة الصحابة (أبو نعيم)",
    9351: "الطبقات الكبرى (ابن سعد)",
    96165: "الثقات لمن ليس في الكتب الستة",
    5816: "الثقات (ابن حبان)",
    5825: "الثقات (العجلي)",
    1692: "ميزان الاعتدال (الذهبي)",
    36357: "لسان الميزان (ابن حجر)",
    10906: "سير أعلام النبلاء (الذهبي)",  # post-Six-Books محدّثون (الأصم-class) — the A.3 coverage gap
}


@dataclass(frozen=True, slots=True)
class BookRecord:
    id: int
    name: str
    author_id: int
    cat_id: int
    page_count: int
    size: int
    has_pdf: bool


@dataclass(frozen=True, slots=True)
class CategoryRecord:
    id: int
    name: str
    book_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class AuthorRecord:
    id: int
    name: str
    death: int | None


@dataclass(slots=True)
class Catalog:
    cats: dict[int, CategoryRecord]
    books: dict[int, BookRecord]
    authors: dict[int, AuthorRecord]
    version: Any = None
    date: Any = None

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> "Catalog":
        cats = {
            int(k): CategoryRecord(int(v["id"]), v["name"], tuple(v.get("books", [])))
            for k, v in data.get("cats", {}).items()
        }
        books = {
            int(k): BookRecord(
                id=int(v["id"]),
                name=v["name"],
                author_id=int(v.get("author_id", 0)),
                cat_id=int(v.get("cat_id", 0)),
                page_count=int(v.get("page_count", 0)),
                size=int(v.get("size", 0)),
                has_pdf=bool(v.get("has_pdf", False)),
            )
            for k, v in data.get("books", {}).items()
        }
        authors = {
            int(k): AuthorRecord(int(v["id"]), v["name"], v.get("death"))
            for k, v in data.get("authors", {}).items()
        }
        return cls(cats, books, authors, data.get("version"), data.get("date"))

    def books_in_categories(self, cat_ids: Iterable[int]) -> list[BookRecord]:
        wanted = set(cat_ids)
        return [b for b in self.books.values() if b.cat_id in wanted]

    def commentaries_for(self, collection_id: int) -> list[BookRecord]:
        """The curated شروح (commentaries) that explain a given base collection."""
        return [self.books[s] for s in COMMENTARIES.get(collection_id, []) if s in self.books]

    def select(
        self,
        *,
        book_ids: Iterable[int] | None = None,
        cat_ids: Iterable[int] | None = None,
        priority: bool = False,
        with_commentaries: bool = False,
    ) -> list[BookRecord]:
        """Resolve a download selection.

        Resolution order: explicit ``book_ids`` → ``priority`` core collections →
        all books in ``cat_ids``. With ``with_commentaries`` the curated شروح of every
        selected base collection are appended (the scholars' explanations).
        """
        if book_ids is not None:
            return [self.books[bid] for bid in book_ids if bid in self.books]

        ordered: list[BookRecord] = []
        seen: set[int] = set()

        def add(book: BookRecord | None) -> None:
            if book and book.id not in seen:
                ordered.append(book)
                seen.add(book.id)

        if priority:
            for bid in CORE_COLLECTIONS:
                add(self.books.get(bid))
            for bid in RIJAL_SOURCES:   # the رجال grading sources (prose network books fetched on demand)
                add(self.books.get(bid))
        if cat_ids is not None:
            for book in self.books_in_categories(cat_ids):
                add(book)
        if with_commentaries:
            for base_id in [b.id for b in list(ordered)]:
                for sharh in self.commentaries_for(base_id):
                    add(sharh)
        return ordered

    def total_pages(self, books: Iterable[BookRecord]) -> int:
        return sum(b.page_count for b in books)
