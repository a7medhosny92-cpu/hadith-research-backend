"""قواعد تمييز المهمل — the classical, curated disambiguations a محدّث applies when a chain cites a
homonym by a bare name: the man is fixed by his **شيخ** (whom he narrates FROM).

«سفيانُ عن عمرِو بنِ دينار» is ابنُ عيينة؛ «سفيانُ عن الأعمش/منصور» is الثوريُّ. «حمادٌ عن أيوب» is ابنُ
زيد؛ «حمادٌ عن ثابت/حميد» is ابنُ سلمة. «هشامٌ عن أبيه» is ابنُ عروة؛ «عن قتادة» is الدستوائيُّ.

These are DETERMINISTIC rules of the science — not a heuristic over the (noisy) corpus graph — so they
resolve the famous «مشترك» the graph leaves ambiguous, at high confidence. The table is intentionally
CONSERVATIVE: only DISTINCTIVE شيوخ are listed (دينار for «عمرو بن دينار», not the ambiguous «عمرو»),
and a شيخ shared by both homonyms is omitted, so an unmatched شيخ is left ambiguous (لا نختلق). Extend
by adding a `(bare ism → [(distinctive شيخ markers, full canonical name)])` qā'ida.
"""

from __future__ import annotations

from app.parsing.normalize import normalize_for_search


def _f(s: str) -> str:
    return normalize_for_search(s)


def _markers(*names: str) -> frozenset[str]:
    return frozenset(_f(n) for n in names)


# bare folded ism  →  ordered [(distinctive شيخ markers, full canonical name)]. A marker matches when it
# is a whole folded token of the شيخ (single word) or a contiguous substring of his folded name (phrase).
_QAIDA: dict[str, list[tuple[frozenset[str], str]]] = {
    _f("سفيان"): [
        (_markers("دينار", "الزهري", "المنكدر", "الزناد", "علاقة", "ابي يزيد", "صفوان بن سليم"),
         "سفيان بن عيينة"),
        (_markers("الاعمش", "منصور", "ابي اسحاق", "كهيل", "حبيب بن ابي ثابت", "السدي", "ابي حصين", "زبيد"),
         "سفيان بن سعيد الثوري"),
    ],
    _f("حماد"): [
        (_markers("ايوب", "عبيد الله بن عمر", "شنظير", "كثير بن شنظير", "يحيى بن سعيد"),
         "حماد بن زيد"),
        (_markers("ثابت", "حميد", "علي بن زيد", "قتادة", "عمار بن ابي عمار", "ابي طلحة", "العشراء",
                  "خثيم", "الجريري", "اسحاق بن عبد الله"),
         "حماد بن سلمة"),
    ],
    _f("هشام"): [
        (_markers("ابيه", "عروة", "وهب بن كيسان"), "هشام بن عروة"),
        (_markers("قتادة", "يحيى بن ابي كثير", "ابي الزبير"), "هشام الدستوائي"),
        (_markers("ابن سيرين", "محمد بن سيرين", "الحسن", "عكرمة", "حفصة بنت سيرين"), "هشام بن حسان"),
    ],
}


def resolve_qaida(name: str, shaykh: str) -> str | None:
    """Resolve a homonym cited as the bare ``name`` by its ``shaykh`` (the next man on the route), via
    the curated قواعد. Returns the full canonical name, or ``None`` when no rule applies — leave it to
    the graph. Only an EXACT bare ism fires (a name already carrying a nasab/nisba is not ambiguous)."""
    rules = _QAIDA.get(_f(name).strip())
    if not rules:
        return None
    sh = _f(shaykh)
    toks = set(sh.split())
    for markers, full in rules:
        for m in markers:
            if (m in toks) if " " not in m else (m in sh):
                return full
    return None
