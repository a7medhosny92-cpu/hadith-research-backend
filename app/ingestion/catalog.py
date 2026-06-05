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
}

#: Flat, de-duplicated list of every curated commentary book id.
ALL_COMMENTARY_IDS: tuple[int, ...] = tuple(
    dict.fromkeys(sid for ids in COMMENTARIES.values() for sid in ids)
)


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
