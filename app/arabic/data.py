"""Loader for the structured Arabic knowledge base (the JSON in ./knowledge).

Files are read once and cached. This is the single access point so the rest of
the engine never touches the JSON directly.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


@lru_cache(maxsize=None)
def _load(name: str) -> Any:
    path = KNOWLEDGE_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def letters() -> dict:
    return _load("letters")


def sifat() -> dict:
    return _load("sifat")


def tajweed() -> dict:
    return _load("tajweed")


def awzan() -> dict:
    return _load("awzan")


def levels() -> dict:
    return _load("levels")


def vocabulary() -> dict:
    return _load("vocabulary")


def nahw() -> dict:
    return _load("nahw")


def verbs() -> dict:
    return _load("verbs")


def exercises() -> dict:
    return _load("exercises")
