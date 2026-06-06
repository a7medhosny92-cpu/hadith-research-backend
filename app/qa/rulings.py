"""Scholars' rulings on a hadith (أحكام المحدّثين) — extracted from the texts.

A hadith's grade is rarely single: critics differ (صحيح to one, ضعيف to another).
This module recognises *attributed* verdicts in the commentary/takhrij text —
«صحّحه ابن حجر», «قال الترمذي: حسن صحيح», «ضعّفه الألباني» — and *implicit* ones
(«رواه البخاري» → صحيح عنده; «على شرط الشيخين»). Each verdict is tied to its scholar
and the scholar's death year, so rulings can be ordered by طبقة — from the
المتقدّمون (early generations) down to the المعاصرون.

Heuristic and corpus-bound: it surfaces the verdicts *present in the texts you have*;
more شروح/تخريج/علل ⇒ more rulings. Not a substitute for a hand-curated أحكام database.
"""

from __future__ import annotations

from app.parsing.normalize import normalize_for_search

#: Hadith critic → (death year AH, name forms). Ordered roughly by era; the year is
#: what we sort by (طبقات). Forms are matched against the text (folded).
SCHOLARS: dict[str, tuple[int, list[str]]] = {
    "الشافعي": (204, ["الشافعي"]),
    "ابن معين": (233, ["ابن معين", "يحيى بن معين"]),
    "أحمد بن حنبل": (241, ["ابن حنبل", "الإمام أحمد", "أحمد بن حنبل"]),
    "البخاري": (256, ["البخاري", "محمد بن إسماعيل"]),
    "مسلم": (261, ["مسلم بن الحجاج", "الإمام مسلم", "مسلم"]),
    "أبو زرعة الرازي": (264, ["أبو زرعة"]),
    "أبو داود": (275, ["أبو داود"]),
    "أبو حاتم الرازي": (277, ["أبو حاتم"]),
    "الترمذي": (279, ["الترمذي"]),
    "النسائي": (303, ["النسائي"]),
    "ابن خزيمة": (311, ["ابن خزيمة"]),
    "العقيلي": (322, ["العقيلي"]),
    "ابن حبان": (354, ["ابن حبان"]),
    "الطبراني": (360, ["الطبراني"]),
    "الدارقطني": (385, ["الدارقطني"]),
    "الحاكم": (405, ["الحاكم"]),
    "البيهقي": (458, ["البيهقي"]),
    "ابن حزم": (456, ["ابن حزم"]),
    "ابن عبد البر": (463, ["ابن عبد البر"]),
    "البغوي": (516, ["البغوي"]),
    "عبد الحق الإشبيلي": (581, ["عبد الحق", "الإشبيلي"]),
    "ابن الجوزي": (597, ["ابن الجوزي"]),
    "ابن الصلاح": (643, ["ابن الصلاح"]),
    "المنذري": (656, ["المنذري"]),
    "النووي": (676, ["النووي"]),
    "ابن دقيق العيد": (702, ["ابن دقيق"]),
    "ابن تيمية": (728, ["ابن تيمية"]),
    "المزي": (742, ["المزي"]),
    "الذهبي": (748, ["الذهبي"]),
    "الزيلعي": (762, ["الزيلعي"]),
    "ابن كثير": (774, ["ابن كثير"]),
    "العراقي": (806, ["العراقي", "زين الدين العراقي"]),
    "الهيثمي": (807, ["الهيثمي"]),
    "ابن حجر العسقلاني": (852, ["ابن حجر", "العسقلاني"]),
    "البوصيري": (840, ["البوصيري"]),
    "السيوطي": (911, ["السيوطي"]),
    "أحمد شاكر": (1377, ["أحمد شاكر"]),
    "الألباني": (1420, ["الألباني"]),
    "ابن باز": (1420, ["ابن باز"]),
    "شعيب الأرناؤوط": (1438, ["الأرناؤوط", "شعيب الأرناؤوط"]),
    "الوادعي": (1422, ["الوادعي", "مقبل بن هادي"]),
}

# Pre-folded name forms, longest (most specific) first.
_FORMS: list[tuple[str, frozenset[str]]] = sorted(
    ((name, frozenset(normalize_for_search(f).split()))
     for name, (_, forms) in SCHOLARS.items() for f in forms),
    key=lambda p: -len(p[1]),
)

# Judgement verbs (folded) → verdict. We keep the ـه-pronoun forms (clearly verbs:
# «صحّحه فلان») and avoid bare forms that double as common words (حسن، ضعف).
_VERBS: dict[str, str] = {
    "صحح": "صحيح", "صححه": "صحيح", "يصحح": "صحيح",
    "حسنه": "حسن",
    "ضعفه": "ضعيف", "يضعف": "ضعيف",
    "اعله": "معلّ",
    "انكره": "منكر",
    "جوده": "جيد", "جود": "جيد",
    "وضعه": "موضوع",
}
# Standalone verdict words (for «قال فلان: …»).
_VERDICT_WORDS = {
    "صحيح": "صحيح", "حسن": "حسن", "ضعيف": "ضعيف", "موضوع": "موضوع",
    "منكر": "منكر", "شاذ": "شاذ", "ثابت": "صحيح", "باطل": "باطل", "جيد": "جيد",
}
_SAYS = {"قال", "ذكر", "حكم", "قاله"}
_TAKHRIJ_VERBS = {"اخرجه", "رواه", "اخرج", "روي", "اخرجاه"}


def _dewaw(tok: str) -> str:
    """Drop a leading conjunction و/ف so «وصحّحه»/«فضعّفه»/«وقال» match the base trigger."""
    return tok[1:] if len(tok) > 2 and tok[0] in ("و", "ف") else tok


def _scholar_in(window: list[str]) -> str | None:
    """The known scholar that starts *earliest* in the window (i.e. nearest the verb),
    so «قال الترمذي … ابن حجر» attributes to الترمذي, not the farther ابن حجر."""
    toks = [_dewaw(t) for t in window]
    present = set(toks)
    best, best_pos = None, len(toks) + 1
    for name, forms in _FORMS:
        if forms <= present:
            pos = min(toks.index(t) for t in forms)
            if pos < best_pos:
                best, best_pos = name, pos
    return best


def _verdict_in(window: list[str]) -> str | None:
    for i, tok in enumerate(window):
        if tok == "حسن" and i + 1 < len(window) and window[i + 1] == "صحيح":
            return "حسن صحيح"
        if tok in _VERDICT_WORDS:
            return _VERDICT_WORDS[tok]
    return None


def extract_rulings(text: str) -> list[dict]:
    """Attributed/implicit verdicts in ``text``, sorted by the scholar's era (طبقة).

    Each item: ``{scholar, year, verdict, basis}`` where ``basis`` is نصّ (stated),
    تخريج (implied by who reported it) or شرط (on the Shaykhayn's condition)."""
    toks = normalize_for_search(text or "").split()
    rulings: dict[tuple[str, str], str] = {}

    for i, raw in enumerate(toks):
        tok = _dewaw(raw)
        window = toks[i + 1 : i + 5]   # the attributed scholar sits right after the trigger
        # «صحّحه ابن حجر», «ضعّفه الألباني»
        if tok in _VERBS:
            who = _scholar_in(window)
            if who:
                rulings.setdefault((who, _VERBS[tok]), "نصّ")
        # «قال الترمذي: حسن صحيح»
        elif tok in _SAYS:
            who = _scholar_in(window)
            if who:
                verdict = _verdict_in(toks[i + 1 : i + 12])
                if verdict:
                    rulings.setdefault((who, verdict), "نصّ")
        # implicit: «رواه البخاري» → صحيح عنده
        elif tok in _TAKHRIJ_VERBS:
            who = _scholar_in(window)
            if who in ("البخاري", "مسلم"):
                rulings.setdefault((who, "صحيح"), "تخريج")
        # «على شرط الشيخين / البخاري / مسلم»
        elif tok == "شرط":
            nxt = set(window)
            if {"الشيخين"} <= nxt or {"البخاري", "مسلم"} <= nxt:
                rulings.setdefault(("البخاري", "صحيح"), "شرط")
                rulings.setdefault(("مسلم", "صحيح"), "شرط")
            elif "البخاري" in nxt:
                rulings.setdefault(("البخاري", "صحيح"), "شرط")
            elif "مسلم" in nxt:
                rulings.setdefault(("مسلم", "صحيح"), "شرط")

    out = [
        {
            "scholar": who,
            "year": SCHOLARS[who][0],
            "era": f"{SCHOLARS[who][0]}هـ",
            "verdict": verdict,
            "basis": basis,
        }
        for (who, verdict), basis in rulings.items()
    ]
    out.sort(key=lambda r: r["year"])
    return out


def collect_rulings(texts: list[str]) -> list[dict]:
    """Merge rulings found across several texts (matn + شروح …), de-duplicated, by era.

    When a scholar is cited with conflicting verdicts across texts, both are kept —
    divergence is the point."""
    merged: dict[tuple[str, str], dict] = {}
    for text in texts:
        for r in extract_rulings(text):
            merged.setdefault((r["scholar"], r["verdict"]), r)
    return sorted(merged.values(), key=lambda r: r["year"])


def has_divergence(rulings: list[dict]) -> bool:
    """True if the scholars disagree (more than one distinct verdict)."""
    return len({r["verdict"] for r in rulings}) > 1
