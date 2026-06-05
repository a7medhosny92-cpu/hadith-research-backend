"""Ṣarf engine: conjugation + derived nouns (mushtaqqāt) + root/pattern id.

Scope (deliberate, to stay correct): SOUND trilateral verbs (الصحيح السالم) —
no weak radical (و/ي/ا), no hamza, and R2 ≠ R3. For those the paradigm is fully
regular and we generate the complete māḍī / muḍāriʿ (marfūʿ) / amr across the 13
pronouns for Forms I–VIII and X, the three core mushtaqqāt (active/passive
participle + maṣdar), and we handle Form VIII's tāʾ-infix assimilation. Weak /
hamzated / doubled verbs are detected and reported as out of scope rather than
producing wrong output.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List


def _nfc(s: str) -> str:
    # Canonical order for combining marks (e.g. shadda+fatḥa) so generated words
    # compare equal to normally-typed Arabic.
    return unicodedata.normalize("NFC", s)

# diacritics / letters
FATHA, DAMMA, KASRA = "َ", "ُ", "ِ"
SUKUN, SHADDA = "ْ", "ّ"
ALIF = "ا"
WEAK = set("اوىيءأإؤئآ")

PRONOUNS: List[tuple] = [
    ("3ms", "هو"), ("3fs", "هي"), ("3md", "هما"), ("3fd", "هما (مؤ)"),
    ("3mp", "هم"), ("3fp", "هنّ"),
    ("2ms", "أنتَ"), ("2fs", "أنتِ"), ("2d", "أنتما"),
    ("2mp", "أنتم"), ("2fp", "أنتنّ"),
    ("1s", "أنا"), ("1p", "نحن"),
]

# māḍī endings: (ḥaraka on R3, suffix)
_MADI = {
    "3ms": (FATHA, ""), "3fs": (FATHA, "تْ"), "3md": (FATHA, ALIF),
    "3fd": (FATHA, "تَا"), "3mp": (DAMMA, "وا"), "3fp": (SUKUN, "نَ"),
    "2ms": (SUKUN, "تَ"), "2fs": (SUKUN, "تِ"), "2d": (SUKUN, "تُمَا"),
    "2mp": (SUKUN, "تُمْ"), "2fp": (SUKUN, "تُنَّ"),
    "1s": (SUKUN, "تُ"), "1p": (SUKUN, "نَا"),
}

# muḍāriʿ marfūʿ: (personal prefix, ḥaraka on R3, suffix)
_MUDARI = {
    "3ms": ("ي", DAMMA, ""), "3fs": ("ت", DAMMA, ""),
    "3md": ("ي", FATHA, "انِ"), "3fd": ("ت", FATHA, "انِ"),
    "3mp": ("ي", DAMMA, "ونَ"), "3fp": ("ي", SUKUN, "نَ"),
    "2ms": ("ت", DAMMA, ""), "2fs": ("ت", KASRA, "ينَ"),
    "2d": ("ت", FATHA, "انِ"), "2mp": ("ت", DAMMA, "ونَ"),
    "2fp": ("ت", SUKUN, "نَ"), "1s": ("أ", DAMMA, ""), "1p": ("ن", DAMMA, ""),
}

# amr (2nd person): (ḥaraka on R3, suffix) — like the muḍāriʿ majzūm
_AMR = {
    "2ms": (SUKUN, ""), "2fs": (KASRA, "ي"), "2d": (FATHA, ALIF),
    "2mp": (DAMMA, "وا"), "2fp": (SUKUN, "نَ"),
}


class UnsupportedVerb(ValueError):
    pass


@dataclass
class Pattern:
    madi_stem: str   # past stem up to & incl. R2's past vowel (R3 + ending added)
    mud_pv: str      # vowel after the personal prefix in the muḍāriʿ
    mud_pre: str     # present stem after the prefix vowel, up to R2 (no R2 vowel)
    mud_v2: str      # R2's present vowel
    onset: str       # imperative onset: 'wasl' | 'qat' | 'none'
    masdar: str      # full maṣdar (or 'سماعي' for Form I)


@dataclass
class Conjugation:
    root: List[str]
    form: int
    madi: Dict[str, str] = field(default_factory=dict)
    mudari: Dict[str, str] = field(default_factory=dict)
    amr: Dict[str, str] = field(default_factory=dict)
    mushtaqqat: Dict[str, str] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {"root": self.root, "form": self.form, "madi": self.madi,
                "mudari": self.mudari, "amr": self.amr,
                "mushtaqqat": self.mushtaqqat, "note": self.note}


def is_sound(root: List[str]) -> bool:
    return (len(root) == 3 and not (set(root) & WEAK) and root[1] != root[2])


_VOWEL = {"a": FATHA, "i": KASRA, "u": DAMMA}


def form1_vowels(root: List[str]):
    """Lexical (madi_v2, mud_v2) for a known Form I verb, or None if unknown.

    The Form I stem vowel is سماعي (memorized, not derivable), so we look it up
    instead of guessing a default that would mis-vocalize the present tense.
    """
    from . import data
    key = "".join(root)
    for v in data.verbs()["verbs"]:
        if v["root"] == key:
            return _VOWEL[v["madi"]], _VOWEL[v["mudari"]]
    return None


def conjugate_auto(root: List[str], form: int = 1) -> "Conjugation":
    """Conjugate, auto-applying the correct Form I vowels when the verb is known.

    For an unknown Form I verb a note is attached (the present vowel is a guess).
    """
    if form == 1:
        vowels = form1_vowels(root)
        if vowels:
            c = conjugate(root, form, madi_v2=vowels[0], mud_v2=vowels[1])
            c.note = "vocali di Forma I dal lessico"
            return c
        c = conjugate(root, form)
        c.note = "verbo non nel lessico: vocale del presente stimata (ḍamma)"
        return c
    return conjugate(root, form)


# Form VIII: assimilation of the infix tāʾ (إبدال تاء الافتعال) by first radical.
_F8_TO_TA = set("صض")     # infix ت → ط (separate, R1 keeps sukūn)
_F8_TO_DAL = set("ز")     # infix ت → د (separate)
_F8_IDGHAM = {"ط": "ط", "ظ": "ظ", "د": "د", "ذ": "د", "ت": "ت", "ث": "ث"}


def _f8_cluster(r1: str, infix_vowel: str) -> str:
    """[R1 + infix] for Form VIII, applying tāʾ-infix assimilation."""
    if r1 in _F8_IDGHAM:                       # geminate, R1 absorbed
        return _F8_IDGHAM[r1] + SHADDA + infix_vowel
    if r1 in _F8_TO_TA:
        return r1 + SUKUN + "ط" + infix_vowel
    if r1 in _F8_TO_DAL:
        return r1 + SUKUN + "د" + infix_vowel
    return r1 + SUKUN + "ت" + infix_vowel      # no assimilation


def _pattern(r1: str, r2: str, r3: str, form: int,
             madi_v2: str, mud_v2: str) -> Pattern:
    F, D, K, S, SH = FATHA, DAMMA, KASRA, SUKUN, SHADDA
    if form == 1:
        return Pattern(r1+F+r2+madi_v2, F, r1+S+r2, mud_v2, "wasl", "سماعي")
    if form == 2:
        return Pattern(r1+F+r2+SH+F, D, r1+F+r2+SH, K, "none",
                       "تَ"+r1+S+r2+K+"ي"+r3)
    if form == 3:
        return Pattern(r1+F+ALIF+r2+F, D, r1+F+ALIF+r2, K, "none",
                       "مُ"+r1+F+ALIF+r2+F+r3+F+"ة")
    if form == 4:
        return Pattern("أَ"+r1+S+r2+F, D, r1+S+r2, K, "qat",
                       "إِ"+r1+S+r2+F+ALIF+r3)
    if form == 5:
        return Pattern("تَ"+r1+F+r2+SH+F, F, "تَ"+r1+F+r2+SH, F, "none",
                       "تَ"+r1+F+r2+SH+D+r3)
    if form == 6:
        return Pattern("تَ"+r1+F+ALIF+r2+F, F, "تَ"+r1+F+ALIF+r2, F, "none",
                       "تَ"+r1+F+ALIF+r2+D+r3)
    if form == 7:
        return Pattern("اِنْ"+r1+F+r2+F, F, "نْ"+r1+F+r2, K, "wasl",
                       "اِنْ"+r1+K+r2+F+ALIF+r3)
    if form == 8:
        cf, ck = _f8_cluster(r1, F), _f8_cluster(r1, K)
        return Pattern("اِ"+cf+r2+F, F, cf+r2, K, "wasl",
                       "اِ"+ck+r2+F+ALIF+r3)
    if form == 10:
        return Pattern("اِسْتَ"+r1+S+r2+F, F, "سْتَ"+r1+S+r2, K, "wasl",
                       "اِسْتِ"+r1+S+r2+F+ALIF+r3)
    raise UnsupportedVerb(f"Forma {form} non supportata (sani: I–VIII, X).")


def conjugate(root: List[str], form: int = 1,
              madi_v2: str = FATHA, mud_v2: str = DAMMA) -> Conjugation:
    """Full paradigm + mushtaqqāt for a sound trilateral verb.

    `madi_v2` / `mud_v2` are the R2 vowels for Form I (lexical: a/i/u); ignored
    for the augmented forms.
    """
    if len(root) != 3:
        raise UnsupportedVerb("Servono esattamente 3 radicali (verbo trilittero).")
    if not is_sound(root):
        raise UnsupportedVerb("Il generatore copre solo i verbi SANI (niente "
                              "lettere deboli/hamza, R2 ≠ R3).")
    r1, r2, r3 = root
    p = _pattern(r1, r2, r3, form, madi_v2, mud_v2)
    c = Conjugation(root=list(root), form=form)

    for key, _ in PRONOUNS:
        h, suf = _MADI[key]
        c.madi[key] = _nfc(p.madi_stem + r3 + h + suf)

    mud_stem = p.mud_pre + p.mud_v2
    for key, _ in PRONOUNS:
        pre, h, suf = _MUDARI[key]
        c.mudari[key] = _nfc(pre + p.mud_pv + mud_stem + r3 + h + suf)

    hamza = ("أَ" if p.onset == "qat"
             else (ALIF + (DAMMA if (form == 1 and mud_v2 == DAMMA) else KASRA))
             if p.onset == "wasl" else "")
    for key in ("2ms", "2fs", "2d", "2mp", "2fp"):
        h, suf = _AMR[key]
        c.amr[key] = _nfc(hamza + mud_stem + r3 + h + suf)

    c.mushtaqqat = _mushtaqqat(r1, r2, r3, form, p, madi_v2)
    return c


def _mushtaqqat(r1, r2, r3, form, p: Pattern, madi_v2: str) -> Dict[str, str]:
    if form == 1:
        out = {
            "اسم الفاعل": r1 + FATHA + ALIF + r2 + KASRA + r3,        # فاعِل
            "اسم المفعول": "مَ" + r1 + SUKUN + r2 + DAMMA + "و" + r3,  # مفعول
            "المصدر": "سماعي",
        }
    else:
        out = {
            "اسم الفاعل": "مُ" + p.mud_pre + KASRA + r3,
            "اسم المفعول": "مُ" + p.mud_pre + FATHA + r3,
            "المصدر": p.masdar,
        }
    return {k: _nfc(v) for k, v in out.items()}


def mushtaqqat(root: List[str], form: int = 1, madi_v2: str = FATHA,
               mud_v2: str = DAMMA) -> Dict[str, str]:
    """The three core derived nouns for a sound verb."""
    if not is_sound(root):
        raise UnsupportedVerb("Solo verbi sani.")
    r1, r2, r3 = root
    p = _pattern(r1, r2, r3, form, madi_v2, mud_v2)
    return _mushtaqqat(r1, r2, r3, form, p, madi_v2)


# --- root / wazn identification (best-effort) -------------------------------

def identify(word: str) -> dict:
    """Best-effort guess of (form, radicals) from a verb's bare skeleton.

    Arabic morphology is ambiguous without vowels (e.g. Forms I and II share a
    3-consonant skeleton), so this returns candidate forms, not a single answer.
    """
    from app.pipeline.i18n import strip_tashkeel
    bare = strip_tashkeel(word).strip()
    n = len(bare)
    candidates: List[dict] = []

    def add(form, radicals):
        radicals = list(radicals)
        if len(radicals) == 3 and not (set(radicals) & WEAK):
            candidates.append({"form": form, "root": radicals})

    if bare.startswith("است") and n == 6:
        add(10, bare[3:])
    if bare.startswith("ان") and n == 5:
        add(7, bare[2:])
    if bare.startswith("ت") and n == 5:
        add(5, bare[1:4])                       # تفعّل
        add(6, [bare[1], bare[3], bare[4]])     # تفاعل
    if bare.startswith("ا") and n == 5 and bare[2] in {"ت", "ط", "د"}:
        add(8, [bare[1], bare[3], bare[4]])     # افتعل (+ assimilated ط/د infix)
    if (bare.startswith("أ") or bare.startswith("ا")) and n == 4:
        add(4, bare[1:])                        # أفعل
    if n == 4 and bare[1] == "ا":
        add(3, [bare[0], bare[2], bare[3]])     # فاعل
    if n == 3:
        add(1, bare)
        add(2, bare)                            # فعّل shares the skeleton

    seen, out = set(), []
    for c in candidates:
        k = (c["form"], tuple(c["root"]))
        if k not in seen:
            seen.add(k)
            out.append(c)
    return {"input": word, "bare": bare, "candidates": out}
