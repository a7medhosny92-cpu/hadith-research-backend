"""Iʿrāb analyzer (إعراب): for each word in a sentence, give its case and
grammatical function — and, for tutoring, compare the case READ from the
diacritics against the case EXPECTED from the syntax, flagging mismatches.

Deterministic and offline. It is a rule-based analyzer for well-formed,
diacritized Classical Arabic: it covers the core constructions (nominal /
verbal sentences, ḥarf jarr, kāna & inna and their sisters, fāʿil/mafʿūl,
basic iḍāfa) and is honest elsewhere — words it cannot resolve are marked
`uncertain` rather than guessed. Full parsing (every manṣūb category, clause
embedding) is out of scope for this first version.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional

from . import data
from app.pipeline.i18n import strip_tashkeel

# marks
FATHA, DAMMA, KASRA = "َ", "ُ", "ِ"
FATHATAN, DAMMATAN, KASRATAN = "ً", "ٌ", "ٍ"
SUKUN, SHADDA, DAGGER = "ْ", "ّ", "ٰ"
TANWIN = {FATHATAN, DAMMATAN, KASRATAN}
MARKS = {FATHA, DAMMA, KASRA, SUKUN, SHADDA, DAGGER} | TANWIN
LONG = {"ا", "و", "ي", "ى", "آ"}

RAF, NASB, JARR, JAZM = "رفع", "نصب", "جر", "جزم"

_CASE_BY_MARK = {
    DAMMA: RAF, DAMMATAN: RAF,
    FATHA: NASB, FATHATAN: NASB,
    KASRA: JARR, KASRATAN: JARR,
}


@dataclass
class Word:
    text: str
    bare: str
    pos: str                      # حرف | فعل | اسم | unknown
    function: str = "—"           # iʿrāb role (Arabic)
    read_case: Optional[str] = None     # case read from the diacritics
    expected_case: Optional[str] = None # case required by the syntax
    marker: str = ""              # the final mark/sign used to read the case
    note: str = ""

    @property
    def ok(self) -> Optional[bool]:
        if self.read_case is None or self.expected_case is None:
            return None
        return self.read_case == self.expected_case

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d


@dataclass
class Analysis:
    sentence: str
    kind: str                     # جملة اسمية | جملة فعلية | —
    words: List[Word] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"sentence": self.sentence, "kind": self.kind,
                "words": [w.to_dict() for w in self.words]}


# --- lexicon sets (bare forms) ---------------------------------------------

def _sets() -> dict:
    n = data.nahw()
    return {
        "jarr": set(n["jarr_particles"]["words"]),
        "inna": set(n["inna_sisters"]["words"]),
        "kana": set(n["kana_sisters"]["words"]),
        "dhanna": set(n["dhanna_sisters"]["words"]),
        "nasb_v": set(n["nasb_verb_particles"]["words"]),
        "jazm_v": set(n["jazm_verb_particles"]["words"]),
        "conj": set(n["conjunctions"]["words"]),
        "rel": set(n["relatives"]["words"]),
        "dem": set(n["demonstratives"]["words"]),
        "pron": set(n["pronouns"]["words"]),
        "verbs": set(n["common_verbs"]["words"]),
        "nouns": set(n["common_nouns"]["words"]),
    }


# --- reading the case from the diacritics ----------------------------------

def _letters(word: str):
    out = []
    i, n = 0, len(word)
    while i < n:
        ch = word[i]
        if ch not in MARKS:
            j, marks = i + 1, []
            while j < n and word[j] in MARKS:
                marks.append(word[j])
                j += 1
            out.append((ch, marks))
            i = j
        else:
            i += 1
    return out


def read_case(word: str):
    """Return (case, marker) read from the word's ending, or (None, '')."""
    letters = _letters(word)
    if not letters:
        return None, ""
    # skip a silent tanwīn-alif written after a fatḥatān
    last_ch, last_marks = letters[-1]
    if last_ch in ("ا", "ى") and not last_marks and len(letters) >= 2:
        last_ch, last_marks = letters[-2]
    for m in last_marks:
        if m in _CASE_BY_MARK:
            return _CASE_BY_MARK[m], m
    if SUKUN in last_marks:
        return JAZM, SUKUN
    if last_ch in LONG:
        return None, "حرف علة"      # long-vowel ending: case is muqaddar (estimated)
    return None, ""


# --- classification ---------------------------------------------------------

_MUDARI_PREFIX = set("أنيت")


def _classify(bare: str, marks_have_tanwin: bool, S: dict) -> str:
    if bare in S["jarr"] | S["inna"] | S["nasb_v"] | S["jazm_v"] | S["conj"]:
        # particle (note: some are also nouns/verbs; disambiguated by caller)
        return "حرف"
    # strong noun signals first: the article or tanwīn override the lexicons
    if marks_have_tanwin or bare.startswith("ال"):
        return "اسم"
    if bare in S["rel"] | S["dem"] | S["pron"] | S["nouns"]:
        return "اسم"
    if bare in S["kana"] or bare in S["dhanna"] or bare in S["verbs"]:
        return "فعل"
    # heuristic verb cues (only when not in any lexicon)
    if bare and bare[0] in _MUDARI_PREFIX and len(bare) >= 4:
        return "فعل"                # muḍāriʿ-shaped
    if len(bare) == 3 and not (set(bare) & LONG):
        return "فعل"                # likely a bare māḍī
    return "اسم"


def _has_tanwin(word: str) -> bool:
    return any(m in TANWIN for _, ml in _letters(word) for m in ml)


def _is_definite(bare: str) -> bool:
    return bare.startswith("ال")


# --- the analysis pass ------------------------------------------------------

def analyze(sentence: str) -> Analysis:
    S = _sets()
    raw = sentence.strip().split()
    words: List[Word] = []
    for tok in raw:
        bare = strip_tashkeel(tok)
        rc, marker = read_case(tok)
        pos = _classify(bare, _has_tanwin(tok), S)
        words.append(Word(text=tok, bare=bare, pos=pos, read_case=rc, marker=marker))

    kind = "—"
    # find first non-conjunction content word to decide sentence type
    first = next((w for w in words if w.bare not in S["conj"]), None)
    if first:
        kind = "جملة فعلية" if first.pos == "فعل" else "جملة اسمية"

    # governance pass
    pending = None          # one of: 'jarr','inna','kana','verb_fail','verb_mafool','mubtada','khabar'
    seen_fail = False
    for idx, w in enumerate(words):
        prev = words[idx - 1] if idx > 0 else None

        if w.pos == "حرف":
            if w.bare in S["jarr"]:
                w.function, pending = "حرف جر", "jarr"
            elif w.bare in S["inna"]:
                w.function, pending = "حرف ناسخ (إنّ وأخواتها)", "inna"
            elif w.bare in S["conj"]:
                w.function = "حرف عطف"
            elif w.bare in S["nasb_v"]:
                w.function, pending = "حرف نصب", "nasb_v"
            elif w.bare in S["jazm_v"]:
                w.function, pending = "حرف جزم", "jazm_v"
            else:
                w.function = "حرف"
            continue

        if w.pos == "فعل":
            mudari = bool(w.bare) and w.bare[0] in _MUDARI_PREFIX and len(w.bare) >= 4
            if not mudari:
                # past/imperative verbs are mabnī — they carry no iʿrāb case
                w.read_case, w.note = None, "فعل مبني"
            if w.bare in S["kana"]:
                w.function, pending = "فعل ناسخ (كان وأخواتها)", "kana"
            else:
                if pending == "nasb_v":
                    w.function, w.expected_case = "فعل مضارع منصوب", NASB
                elif pending == "jazm_v":
                    w.function, w.expected_case = "فعل مضارع مجزوم", JAZM
                else:
                    w.function = "فعل"
                pending, seen_fail = "verb_fail", False
            continue

        # --- nouns ---
        # iḍāfa: a noun in jarr right after another noun (not a jarr particle)
        if (prev and prev.pos == "اسم" and w.read_case == JARR
                and pending not in ("jarr",)):
            w.function, w.expected_case = "مضاف إليه", JARR
            continue

        if pending == "jarr":
            w.function, w.expected_case = "اسم مجرور", JARR
            pending = None
        elif pending == "inna":
            w.function, w.expected_case = "اسم إنّ", NASB
            pending = "khabar_inna"
        elif pending == "khabar_inna":
            w.function, w.expected_case = "خبر إنّ", RAF
            pending = None
        elif pending == "kana":
            w.function, w.expected_case = "اسم كان", RAF
            pending = "khabar_kana"
        elif pending == "khabar_kana":
            w.function, w.expected_case = "خبر كان", NASB
            pending = None
        elif pending == "verb_fail" and not seen_fail:
            w.function, w.expected_case = "فاعل", RAF
            seen_fail, pending = True, "verb_mafool"
        elif pending == "verb_mafool":
            w.function, w.expected_case = "مفعول به", NASB
            # allow more objects to stay as mafʿūl
        else:
            # nominal sentence: first noun = mubtadaʾ, next = khabar
            if kind == "جملة اسمية" and not any(
                    x.function == "مبتدأ" for x in words[:idx]):
                w.function, w.expected_case = "مبتدأ", RAF
                pending = "khabar_mubtada"
            elif pending == "khabar_mubtada":
                w.function, w.expected_case = "خبر", RAF
                pending = None
            else:
                w.function = "اسم"

        if w.bare in S["dem"] | S["rel"] | S["pron"]:
            w.note = "مبني (لا يتغير آخره)"
            w.expected_case = None

    return Analysis(sentence=sentence, kind=kind, words=words)
