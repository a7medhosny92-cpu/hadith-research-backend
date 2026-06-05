"""CLI for the offline Arabic engine — analyze tajwīd and inspect letters.

    python3 arabic_cli.py tajweed "بِسْمِ اللَّهِ الرَّحْمٰنِ الرَّحِيمِ"
    python3 arabic_cli.py letter ض
    python3 arabic_cli.py levels
    python3 arabic_cli.py conjugate ك ت ب 1
    python3 arabic_cli.py word استغفر
"""

from __future__ import annotations

import sys

from app.arabic import data, phonology, tajweed, morphology


def cmd_tajweed(text: str) -> None:
    findings = tajweed.analyze(text)
    print(f"\n  النص: {text}\n")
    if not findings:
        print("  (nessuna regola rilevata — fornisci testo vocalizzato)")
        return
    for f in findings:
        print(f"  • {f.name:18} [{f.key:18}] {f.letters:12} — {f.explanation}")
    print(f"\n  {len(findings)} regole rilevate.\n")


def cmd_letter(letter: str) -> None:
    L = phonology.get(letter)
    if not L:
        print(f"  '{letter}' non è una lettera nota.")
        return
    print(f"\n  {L.letter}  {L.name} ({L.translit}) /{L.ipa}/")
    print(f"  Makhraj : {L.region_label}")
    print(f"  Tipo    : {'مفخّمة (pesante)' if L.heavy else 'مرققة (leggera)'}"
          f"{' · حرف مد' if L.madd else ''}"
          f"{' · حرف شمسي' if L.sun else ' · حرف قمري'}")
    print(f"  Ṣifāt   : {'، '.join(L.sifat)}\n")


def cmd_levels() -> None:
    print()
    for lv in data.levels()["levels"]:
        print(f"  {lv['id']} ({lv['cefr']}) — متن: {lv['matn']}")
        print(f"      obiettivi: {'؛ '.join(lv['objectives'])}")
    print()


_PRON_ORDER = ["3ms", "3fs", "3md", "3fd", "3mp", "3fp",
               "2ms", "2fs", "2d", "2mp", "2fp", "1s", "1p"]
_LABELS = dict(morphology.PRONOUNS)


def cmd_conjugate(argv) -> None:
    root = argv[:3]
    form = int(argv[3]) if len(argv) > 3 else 1
    try:
        c = morphology.conjugate(root, form)
    except morphology.UnsupportedVerb as e:
        print(f"  {e}")
        return
    print(f"\n  الجذر: {'-'.join(root)}   |   الوزن: الصيغة {form}\n")
    for tense, table in (("الماضي", c.madi), ("المضارع", c.mudari)):
        print(f"  ── {tense} ──")
        for key in _PRON_ORDER:
            print(f"     {_LABELS[key]:8} {table[key]}")
    print("  ── الأمر ──")
    for key in ["2ms", "2fs", "2d", "2mp", "2fp"]:
        print(f"     {_LABELS[key]:8} {c.amr[key]}")
    print("  ── المشتقّات ──")
    for name, val in c.mushtaqqat.items():
        print(f"     {name:12} {val}")
    print()


def cmd_word(word: str) -> None:
    res = morphology.identify(word)
    print(f"\n  الكلمة: {res['input']}  (الهيكل: {res['bare']})")
    if not res["candidates"]:
        print("  nessun candidato (forse verbo debole/non standard).\n")
        return
    print("  candidati (forma + radice):")
    for cand in res["candidates"]:
        print(f"     الصيغة {cand['form']:2}  →  {'-'.join(cand['root'])}")
    print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "tajweed" and len(sys.argv) > 2:
        cmd_tajweed(sys.argv[2])
    elif cmd == "letter" and len(sys.argv) > 2:
        cmd_letter(sys.argv[2])
    elif cmd == "levels":
        cmd_levels()
    elif cmd == "conjugate" and len(sys.argv) > 4:
        cmd_conjugate(sys.argv[2:])
    elif cmd == "word" and len(sys.argv) > 2:
        cmd_word(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
