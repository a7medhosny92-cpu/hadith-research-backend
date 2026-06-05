"""Self-contained Arabic text utilities for the tutor package.

Kept here (instead of importing from elsewhere) so `app.arabic` has no external
dependencies and can live in its own repository.
"""

from __future__ import annotations

import re

# Arabic diacritics by explicit Unicode codepoints (ASCII-safe source):
# harakat/tanwin/shadda/sukun (U+064B-U+065F), superscript alef (U+0670),
# Quranic marks (U+0610-U+061A, U+06D6-U+06ED) and tatweel (U+0640).
_TASHKEEL = re.compile(
    "[ؐ-ًؚ-ٰٟـ"
    "ۖ-ۜ۟-۪ۤۧۨ-ۭ]"
)


def strip_tashkeel(s: str) -> str:
    """Remove Arabic diacritics, leaving the bare letters."""
    return _TASHKEEL.sub("", s)
