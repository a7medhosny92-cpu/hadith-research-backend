"""Phonology lookups: per-letter makhraj (articulation) and ṣifāt (attributes).

Each letter's ṣifāt are derived from the group-membership in sifat.json (single
source of truth) rather than duplicated per letter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional

from . import data


@dataclass
class Letter:
    letter: str
    name: str
    translit: str
    ipa: str
    region: str            # jawf | halq | lisan | shafatan | khayshum
    region_label: str
    sun: bool              # sun letter (assimilates the article's lām)
    madd: bool
    sifat: List[str] = field(default_factory=list)   # human-readable attributes
    heavy: bool = False    # mufakhkham (istiʿlāʾ) vs light (istifāl)


@lru_cache(maxsize=1)
def _letter_index() -> Dict[str, dict]:
    return {l["letter"]: l for l in data.letters()["letters"]}


def _all_letters() -> List[str]:
    return [l["letter"] for l in data.letters()["letters"]]


@lru_cache(maxsize=1)
def _sifat_map() -> Dict[str, List[str]]:
    """letter -> list of attribute labels (e.g. 'جهر', 'شدة', 'قلقلة')."""
    out: Dict[str, List[str]] = {c: [] for c in _all_letters()}
    s = data.sifat()

    # contrasting: assign the named value; "rest" gets the complement
    for group in s["contrasting"].values():
        named = {v["ar"]: v["letters"] for v in group["values"].values()
                 if v["letters"] != "rest"}
        assigned = set()
        for label, letters in named.items():
            for ch in letters:
                if ch in out:
                    out[ch].append(label)
                    assigned.add(ch)
        rest_label = next((v["ar"] for v in group["values"].values()
                           if v["letters"] == "rest"), None)
        if rest_label:
            for ch in _all_letters():
                if ch not in assigned:
                    out[ch].append(rest_label)

    # non-contrasting: only the listed letters get the label
    for attr in s["non_contrasting"].values():
        for ch in attr["letters"]:
            if ch in out:
                out[ch].append(attr["ar"])
    return out


_ISTILA = set("خصضغطقظ")


def get(letter: str) -> Optional[Letter]:
    """Full phonological profile of a single letter, or None if unknown."""
    info = _letter_index().get(letter)
    if not info:
        return None
    regions = data.letters()["regions"]
    return Letter(
        letter=info["letter"], name=info["name"], translit=info["translit"],
        ipa=info["ipa"], region=info["region"],
        region_label=regions.get(info["region"], info["region"]),
        sun=info["sun"], madd=info["madd"],
        sifat=_sifat_map().get(letter, []),
        heavy=letter in _ISTILA,
    )


def is_sun(letter: str) -> bool:
    info = _letter_index().get(letter)
    return bool(info and info["sun"])
