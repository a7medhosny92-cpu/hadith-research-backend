"""Find a turath book id by a title substring, from the LOCALLY CACHED catalog — to pick a new رجال
source to ingest (the صحابة dictionaries, الثقات, …) without dumping the ~2 MB catalog anywhere.

    python -m scripts.find_book                        # the رجال/صحابة shortlist that fills «مجهول»
    python -m scripts.find_book الإصابة "أسد الغابة"     # explicit title substrings

Prints each match as a ready-to-copy «--books <id>» line for `scripts.ingest`.
"""

from __future__ import annotations

import json
import sys

from app.config import get_settings

# Default shortlist: the sources that fill the «مجهول» / coverage gap.
_DEFAULT = [
    "الإصابة", "الاستيعاب", "أسد الغابة", "معرفة الصحابة",          # Companion dictionaries
    "الثقات", "ميزان الاعتدال", "لسان الميزان",                     # broad ثقات + the disputed
    "تاريخ الإسلام", "سير أعلام النبلاء",                           # death-years / biographies
    "تهذيب التهذيب", "تهذيب الكمال", "الجرح والتعديل", "الطبقات الكبرى",
]


def main() -> None:
    queries = sys.argv[1:] or _DEFAULT
    raw = get_settings().raw_dir
    path = next((p for p in (raw / "catalog.json", raw / "data-v3.json") if p.exists()), None)
    if path is None:
        print(f"catalog not found under {raw} — run update.bat (or scripts.ingest) once to cache it.")
        return
    books = json.loads(path.read_text(encoding="utf-8")).get("books", {})
    hits = [(b.get("id"), b.get("cat_id"), b.get("name", ""))
            for b in books.values() if any(q in b.get("name", "") for q in queries)]
    hits.sort(key=lambda t: (t[1] or 0, t[0] or 0))
    print(f"{len(hits)} match(es) in {path.name} ({len(books)} books):")
    for bid, cat, name in hits:
        print(f"  --books {bid:<7} · cat {cat} · {name}")


if __name__ == "__main__":
    main()
