"""Quiz engine: generates exercises whose answers the deterministic engine
already knows (conjugation, tajwīd, iʿrāb case, letters, vocabulary), checks the
learner's answer, and explains it.

Design: every item is multiple-choice with a server-side answer. The generator
returns a *public* view (no answer); the answer + explanation are kept in a
small in-memory store keyed by the item id, looked up by `check()`. This keeps
the quiz reliable — we never ask about something the engine can't resolve.
"""

from __future__ import annotations

import random
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from . import data, phonology, tajweed, morphology, iraab

TYPES = ["conjugation", "tajweed", "iraab", "letter", "vocabulary"]
TYPE_LABELS = {
    "conjugation": "الصرف · Coniugazione",
    "tajweed": "التجويد · Tajwīd",
    "iraab": "الإعراب · Iʿrāb",
    "letter": "الحروف · Lettere",
    "vocabulary": "المفردات · Lessico",
}

_TENSES = {"madi": "الماضي", "mudari": "المضارع", "amr": "الأمر"}
_PR_LABEL = dict(morphology.PRONOUNS)


@dataclass
class Exercise:
    id: str
    type: str
    prompt: str          # Italian instruction
    content: str         # Arabic content to display (RTL)
    choices: List[str]
    answer: int          # index — kept server-side only
    explanation: str

    def public(self) -> dict:
        return {"id": self.id, "type": self.type, "prompt": self.prompt,
                "content": self.content, "choices": self.choices}


# small bounded store: id -> (answer_index, explanation, choices)
_STORE: "OrderedDict[str, tuple]" = OrderedDict()
_STORE_MAX = 500


def _remember(ex: Exercise) -> None:
    _STORE[ex.id] = (ex.answer, ex.explanation, ex.choices)
    while len(_STORE) > _STORE_MAX:
        _STORE.popitem(last=False)


def _mc(rng: random.Random, correct: str, distractors: List[str],
        k: int = 4) -> tuple:
    """Build shuffled choices from a correct answer + distractor pool."""
    pool = [d for d in dict.fromkeys(distractors) if d and d != correct]
    rng.shuffle(pool)
    opts = [correct] + pool[:max(1, k - 1)]
    rng.shuffle(opts)
    return opts, opts.index(correct)


# --- generators -------------------------------------------------------------

def _gen_conjugation(rng: random.Random) -> Exercise:
    verbs = data.verbs()["verbs"]
    v = rng.choice(verbs)
    root = list(v["root"])
    form = rng.choice([1, 2, 4, 8, 10])
    tense = rng.choice(["madi", "mudari", "amr"])
    c = morphology.conjugate_auto(root, form)
    table = getattr(c, tense)
    keys = list(table.keys())
    key = rng.choice(keys)
    correct = table[key]
    distractors = [table[k] for k in keys if k != key]
    choices, ans = _mc(rng, correct, distractors)
    return Exercise(
        id=uuid.uuid4().hex[:12], type="conjugation",
        prompt=f"Coniuga «{v['root']}» (Forma {form}) — {_TENSES[tense]}, "
               f"{_PR_LABEL[key]}:",
        content=v["root"],
        choices=choices, answer=ans,
        explanation=f"{_PR_LABEL[key]} · {_TENSES[tense]} = {correct}")


def _gen_tajweed(rng: random.Random) -> Exercise:
    phrases = data.exercises()["tajweed_phrases"]
    for _ in range(8):
        phrase = rng.choice(phrases)
        findings = [f for f in tajweed.analyze(phrase)
                    if not f.key.startswith("lam_") or rng.random() < 0.5]
        if findings:
            break
    f = rng.choice(findings)
    pool = ["إظهار", "إدغام بغنة", "إدغام بلا غنة", "إقلاب", "إخفاء",
            "قلقلة صغرى", "قلقلة كبرى", "لام شمسية", "لام قمرية",
            "إخفاء شفوي", "إظهار شفوي", "مد متصل (واجب)"]
    choices, ans = _mc(rng, f.name, pool)
    return Exercise(
        id=uuid.uuid4().hex[:12], type="tajweed",
        prompt=f"Quale regola di tajwīd si applica su «{f.letters}»?",
        content=phrase, choices=choices, answer=ans,
        explanation=f"{f.name} — {f.explanation}")


def _gen_iraab(rng: random.Random) -> Exercise:
    sentences = data.exercises()["iraab_sentences"]
    for _ in range(8):
        s = rng.choice(sentences)
        a = iraab.analyze(s)
        targets = [w for w in a.words if w.expected_case and w.function != "—"]
        if targets:
            break
    w = rng.choice(targets)
    case_labels = {iraab.RAF: "رفع", iraab.NASB: "نصب", iraab.JARR: "جر"}
    correct = case_labels.get(w.expected_case, w.expected_case)
    choices, ans = _mc(rng, correct, ["رفع", "نصب", "جر"], k=3)
    return Exercise(
        id=uuid.uuid4().hex[:12], type="iraab",
        prompt=f"Nella frase, quale desinenza (caso) richiede «{w.bare}»?",
        content=s, choices=choices, answer=ans,
        explanation=f"«{w.bare}» è {w.function} → {correct}")


def _gen_letter(rng: random.Random) -> Exercise:
    letters = [l["letter"] for l in data.letters()["letters"]]
    ch = rng.choice(letters)
    L = phonology.get(ch)
    sub = rng.choice(["makhraj", "weight", "sun"])
    if sub == "makhraj":
        labels = list(data.letters()["regions"].values())
        correct = L.region_label
        choices, ans = _mc(rng, correct, labels)
        prompt = f"Qual è il makhraj (luogo di articolazione) di «{ch}»?"
    elif sub == "weight":
        correct = "مفخّمة (pesante)" if L.heavy else "مرققة (leggera)"
        choices, ans = _mc(rng, correct, ["مفخّمة (pesante)", "مرققة (leggera)"], k=2)
        prompt = f"La lettera «{ch}» è pesante o leggera?"
    else:
        correct = "حرف شمسي" if L.sun else "حرف قمري"
        choices, ans = _mc(rng, correct, ["حرف شمسي", "حرف قمري"], k=2)
        prompt = f"«{ch}» è una lettera solare o lunare?"
    return Exercise(
        id=uuid.uuid4().hex[:12], type="letter", prompt=prompt,
        content=ch, choices=choices, answer=ans,
        explanation=f"{L.name} ({L.translit}): {correct}")


def _gen_vocabulary(rng: random.Random) -> Exercise:
    roots = data.vocabulary()["roots"]
    r = rng.choice(roots)
    others = [x["core"] for x in roots if x["root"] != r["root"]]
    choices, ans = _mc(rng, r["core"], others)
    return Exercise(
        id=uuid.uuid4().hex[:12], type="vocabulary",
        prompt=f"Qual è il significato della radice «{r['root']}»?",
        content=r["root"], choices=choices, answer=ans,
        explanation=f"{r['root']} = {r['core']}")


_GENERATORS: Dict[str, Callable[[random.Random], Exercise]] = {
    "conjugation": _gen_conjugation, "tajweed": _gen_tajweed,
    "iraab": _gen_iraab, "letter": _gen_letter, "vocabulary": _gen_vocabulary,
}


def generate(ex_type: Optional[str] = None, seed: Optional[int] = None) -> Exercise:
    rng = random.Random(seed)
    if ex_type in (None, "random", "any"):
        ex_type = rng.choice(TYPES)
    if ex_type not in _GENERATORS:
        raise ValueError(f"Tipo sconosciuto: {ex_type}. Disponibili: {', '.join(TYPES)}")
    ex = _GENERATORS[ex_type](rng)
    _remember(ex)
    return ex


def check(exercise_id: str, choice: int) -> dict:
    if exercise_id not in _STORE:
        raise KeyError("esercizio scaduto o sconosciuto")
    answer, explanation, choices = _STORE[exercise_id]
    correct = (choice == answer)
    return {"correct": correct, "answer": answer,
            "correct_choice": choices[answer] if 0 <= answer < len(choices) else None,
            "explanation": explanation}
