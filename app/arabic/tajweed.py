"""Tajwīd analyzer: given (diacritized) Arabic text, find where the rules apply.

Deterministic and offline. Detects:
  - aḥkām al-nūn al-sākina wa-l-tanwīn (iẓhār, idghām ±ghunna, iqlāb, ikhfāʾ)
  - aḥkām al-mīm al-sākina (ikhfāʾ/idghām shafawī, iẓhār shafawī)
  - al-qalqala (ṣughrā mid-word, kubrā at a stop)
  - al-madd (ṭabīʿī, badal, and a best-effort flag for muttaṣil/lāzim)

Works best on fully vocalized text (as in the muṣḥaf). Returns a list of
findings with the rule, the letters involved, a character span, and an
explanation, so the UI can highlight and the tutor can teach from them.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

from . import data

# Harakat / marks
FATHA, DAMMA, KASRA = "َ", "ُ", "ِ"
FATHATAN, DAMMATAN, KASRATAN = "ً", "ٌ", "ٍ"
SUKUN, SHADDA = "ْ", "ّ"
DAGGER_ALIF = "ٰ"          # ٰ superscript alef — a madd mark, not a base letter
TANWIN = {FATHATAN, DAMMATAN, KASRATAN}
VOWELS = {FATHA, DAMMA, KASRA, SHADDA, DAGGER_ALIF} | TANWIN
HARAKAT = {FATHA, DAMMA, KASRA, SUKUN, SHADDA, DAGGER_ALIF} | TANWIN
MADD_LETTERS = {"ا", "و", "ي", "ى", "آ"}
HAMZA = {"ء", "أ", "إ", "ؤ", "ئ", "آ"}
PREFIXES = {"ب", "ل", "ف", "و", "ك"}   # single-letter proclitics before the article


@dataclass
class Finding:
    rule: str            # category, e.g. "nūn sākina / tanwīn"
    name: str            # the specific ruling in Arabic, e.g. "إدغام بغنة"
    key: str             # machine key, e.g. "idgham_ghunna"
    span: tuple          # (start, end) char indices into the original text
    letters: str         # the trigger + target letters
    explanation: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["span"] = list(self.span)
        return d


def _is_letter(ch: str) -> bool:
    return ch not in HARAKAT and not ch.isspace()


def _tokens(text: str):
    """Yield (index, base_letter, set_of_following_marks) for each base letter."""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if _is_letter(ch):
            j = i + 1
            marks = set()
            while j < n and text[j] in HARAKAT:
                marks.add(text[j])
                j += 1
            yield i, ch, marks
            i = j
        else:
            i += 1


def _next_letter(letters, k: int):
    return letters[k + 1] if k + 1 < len(letters) else None


def _word_start_indices(text: str) -> set:
    """Char indices of letters that begin a word (after space or at the start)."""
    starts, expect = set(), True
    for i, ch in enumerate(text):
        if ch.isspace():
            expect = True
        elif _is_letter(ch):
            if expect:
                starts.add(i)
            expect = False
    return starts


def _group_lookup(rules: dict, target: str) -> Optional[str]:
    for key, spec in rules.items():
        if spec["letters"] != "rest" and target in spec["letters"]:
            return key
    return None


def analyze(text: str) -> List[Finding]:
    tj = data.tajweed()
    nun_rules = tj["nun_sakina_tanwin"]["rules"]
    mim_rules = tj["mim_sakina"]["rules"]
    qalqala_letters = set(tj["qalqala"]["letters"])

    from . import phonology

    letters = list(_tokens(text))   # [(idx, ch, marks), ...]
    word_starts = _word_start_indices(text)
    findings: List[Finding] = []

    for k, (idx, ch, marks) in enumerate(letters):
        nxt = _next_letter(letters, k)
        nxt_ch = nxt[1] if nxt else None
        nxt_idx = nxt[0] if nxt else idx + 1
        prev = letters[k - 1] if k > 0 else None

        # --- lām al-taʿrīf: shamsiyya (assimilated) vs qamariyya (clear) ---
        # the article is alif (word-initial, allowing one proclitic) + lām
        if ch == "ل" and prev and prev[1] == "ا" and nxt_ch:
            alif_idx = prev[0]
            proclitic = (k >= 2 and letters[k - 2][1] in PREFIXES
                         and letters[k - 2][0] in word_starts)
            if alif_idx in word_starts or proclitic:
                if phonology.is_sun(nxt_ch):
                    findings.append(Finding(
                        rule="لام التعريف", name="لام شمسية", key="lam_shamsiyya",
                        span=(idx, nxt_idx + 1), letters=f"ال + {nxt_ch}",
                        explanation="lām non pronunciata; la lettera solare raddoppia"))
                else:
                    findings.append(Finding(
                        rule="لام التعريف", name="لام قمرية", key="lam_qamariyya",
                        span=(idx, nxt_idx + 1), letters=f"ال + {nxt_ch}",
                        explanation="lām pronunciata chiaramente"))

        # --- nūn sākina & tanwīn ---
        is_nun_sakina = ch == "ن" and (SUKUN in marks or not (marks & VOWELS))
        has_tanwin = bool(marks & TANWIN)
        # the ruling applies to the next *pronounced* letter; a silent tanwīn-alif
        # (bare ا/ى written after fatḥatān) is skipped.
        tgt = nxt
        if has_tanwin and nxt and nxt[1] in {"ا", "ى"} and not nxt[2]:
            tgt = _next_letter(letters, k + 1)
        if (is_nun_sakina or has_tanwin) and tgt:
            tgt_ch = tgt[1]
            key = _group_lookup(nun_rules, tgt_ch)
            if key:
                spec = nun_rules[key]
                trigger = "تنوين" if has_tanwin else "ن"
                findings.append(Finding(
                    rule="النون الساكنة والتنوين",
                    name=spec["ar"], key=key,
                    span=(idx, tgt[0] + 1),
                    letters=f"{trigger} + {tgt_ch}",
                    explanation=spec["desc"]))

        # --- mīm sākina ---
        is_mim_sakina = ch == "م" and (SUKUN in marks or not (marks & VOWELS))
        if is_mim_sakina and nxt_ch:
            if nxt_ch == "ب":
                key = "ikhfa_shafawi"
            elif nxt_ch == "م":
                key = "idgham_shafawi"
            else:
                key = "izhar_shafawi"
            spec = mim_rules[key]
            findings.append(Finding(
                rule="الميم الساكنة", name=spec["ar"], key=key,
                span=(idx, nxt_idx + 1), letters=f"م + {nxt_ch}",
                explanation=spec["desc"]))

        # --- qalqala (letter carries sukūn, or is final = at a stop) ---
        if ch in qalqala_letters and (SUKUN in marks or (nxt is None and not (marks & {FATHA, DAMMA, KASRA}))):
            level = "kubra" if nxt is None else "sughra"
            findings.append(Finding(
                rule="القلقلة",
                name="قلقلة " + ("كبرى" if level == "kubra" else "صغرى"),
                key=f"qalqala_{level}",
                span=(idx, idx + 1), letters=ch,
                explanation="rimbalzo/eco sulla lettera con sukūn"
                            + (" in pausa" if level == "kubra" else " a metà parola")))

        # --- madd (best-effort) ---
        if ch in MADD_LETTERS:
            # madd badal: a hamza immediately precedes the madd letter
            prev_ch = letters[k - 1][1] if k > 0 else None
            if ch == "آ" or (prev_ch in HAMZA):
                findings.append(Finding(
                    rule="المد", name="مد بدل", key="madd_badal",
                    span=(idx, idx + 1), letters=ch,
                    explanation="hamza precede la lettera di madd → 2 ḥarakāt"))
            elif nxt_ch in HAMZA:
                findings.append(Finding(
                    rule="المد", name="مد متصل (واجب)", key="madd_muttasil",
                    span=(idx, nxt_idx + 1), letters=f"{ch} + {nxt_ch}",
                    explanation="madd + hamza nella stessa parola → 4–5 ḥarakāt"))
            elif nxt and SHADDA in nxt[2]:
                findings.append(Finding(
                    rule="المد", name="مد لازم", key="madd_lazim",
                    span=(idx, nxt_idx + 1), letters=ch,
                    explanation="madd + sukūn permanente/shadda → 6 ḥarakāt"))

    return findings


def analyze_dicts(text: str) -> List[dict]:
    return [f.to_dict() for f in analyze(text)]
