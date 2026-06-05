"""CLI for the offline Arabic engine — analyze tajwīd and inspect letters.

    python3 arabic_cli.py tajweed "بِسْمِ اللَّهِ الرَّحْمٰنِ الرَّحِيمِ"
    python3 arabic_cli.py letter ض
    python3 arabic_cli.py levels
"""

from __future__ import annotations

import sys

from app.arabic import data, phonology, tajweed


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
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
