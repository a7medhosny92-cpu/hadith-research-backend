"""Joint, anchored تمييز المهمل: resolve a chain's ambiguous narrators *together*, by the
DOCUMENTED شيخ/تلميذ relations (تهذيب الكمال / الجرح والتعديل / الثقات), propagating outward
from the links we are already sure of.

The per-narrator lever (`canon._pick`) decides each ambiguous name on its own, from the
flat token company of its raw neighbours — but those neighbours are themselves ambiguous, so
a bare «عبد الله» beside the name carries no signal, and the company that should disambiguate
is itself in conflict. This pass instead:

  * ANCHORS the links we are sure of (the terminal صحابي; any name that resolves uniquely);
  * for an ambiguous link, keeps only the homonyms DOCUMENTED as a تلميذ of its (resolved)
    شيخ and/or a شيخ of its (resolved) تلميذ — a DIRECTIONAL, identity-level constraint, not
    a token overlap with an ambiguous bag;
  * PROPAGATES: a newly-resolved link becomes an anchor for its neighbours, and we iterate to
    a fixpoint, so certainty spreads generation by generation up the isnād (الصحابي → التابعي →
    تابع التابعي → …) — exactly the way the muḥaddithūn read «تمييز المهمل بالنظر إلى شيخه وتلميذه».

It is POSITIVE-evidence only: a homonym documented in the relation is selected; the ABSENCE of
documentation never rejects a candidate (the rijal books' تلاميذ lists are not exhaustive). When
the surviving set is not a single man, the link is left ``None`` for the caller to HOLD
(يُتوقَّف) — we never guess. Power is bounded by network coverage: a man flanked only by bare
names with no documented network stays the honest floor.
"""

from __future__ import annotations

from app.rijal.index import _clean_seq


def network_key(name: str) -> str:
    """The order-preserving folded key a man is stored/looked-up under in the network
    (يزيد بن جابر ≠ جابر بن يزيد), matching ``canon._candidates``/``build_graph``."""
    return " ".join(_clean_seq(name))


class DocumentedNetwork:
    """Each man's documented شيوخ / تلاميذ (as :func:`network_key` sets), from the prose rijal
    sources. ``students[key]`` = men he taught; ``teachers[key]`` = men he heard from."""

    def __init__(self, teachers: dict[str, set[str]] | None = None,
                 students: dict[str, set[str]] | None = None) -> None:
        self._teachers = teachers or {}
        self._students = students or {}

    def is_student_of(self, student_name: str, teacher_name: str) -> bool:
        """Is ``student_name`` recorded as a تلميذ of ``teacher_name``?"""
        return network_key(student_name) in self._students.get(network_key(teacher_name), frozenset())

    def is_teacher_of(self, teacher_name: str, student_name: str) -> bool:
        """Is ``teacher_name`` recorded as a شيخ of ``student_name``?"""
        return network_key(teacher_name) in self._teachers.get(network_key(student_name), frozenset())

    def __bool__(self) -> bool:
        return bool(self._teachers or self._students)


def resolve_chain(candidates: list[list[str]], anchors: list[str | None],
                  network: DocumentedNetwork) -> list[str | None]:
    """Resolve the ambiguous links of one chain by directional, anchored propagation.

    ``candidates[i]`` — the homonym names for link *i*, in **chain order**: ``[0]`` is the
    collector side (the تلميذ end) and ``[-1]`` is the terminal (الصحابي), each link narrating
    *from* the next (``links[i]`` is the تلميذ of ``links[i+1]``).
    ``anchors[i]`` — a confident name for link *i*, or ``None``.

    Returns ``resolved[i]`` = the chosen name, or ``None`` when the link must be held.
    """
    n = len(candidates)
    resolved: list[str | None] = list(anchors)
    if not network:
        return resolved
    changed = True
    while changed:                       # constraint propagation to a fixpoint
        changed = False
        for i in range(n):
            if resolved[i] or len(candidates[i]) <= 1:
                continue                 # already fixed, or nothing to choose
            shaykh = resolved[i + 1] if i + 1 < n else None     # the link below = my شيخ
            tilmidh = resolved[i - 1] if i - 1 >= 0 else None    # the link above = my تلميذ
            if not (shaykh or tilmidh):
                continue
            supported = {
                c for c in candidates[i]
                if (shaykh and network.is_student_of(c, shaykh))
                or (tilmidh and network.is_teacher_of(c, tilmidh))
            }
            if len(supported) == 1:      # a single documented fit → resolve; else HOLD
                resolved[i] = next(iter(supported))
                changed = True
    return resolved
