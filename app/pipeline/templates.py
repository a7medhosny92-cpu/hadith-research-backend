"""Video templates: different structures + color themes for the script.

Each template turns a topic into a list of `Scene`s with its own pacing,
scene kinds and color palette, in the requested language (see i18n.py).
Selecting a template changes the *structure* of the video (e.g. quiz =
question/answer pairs, top5 = countdown); motion/animation is handled at
render time.

Add a new template by writing a `build_*` function and registering it in
TEMPLATES (and add its strings to every language pack in i18n.py).
"""

from __future__ import annotations

import random
from typing import Callable, Dict, List

from . import i18n
from .script_gen import Scene, Script, _estimate_seconds

# --- color themes: list of (top, bottom, accent) RGB triples ----------------
_THEMES: Dict[str, List[tuple]] = {
    "sunset":  [((255, 94, 98), (255, 195, 113), (20, 20, 30)),
                ((247, 151, 30), (255, 81, 47), (20, 20, 30))],
    "ocean":   [((33, 147, 176), (109, 213, 237), (10, 30, 40)),
                ((0, 91, 154), (0, 180, 219), (255, 255, 255))],
    "neon":    [((131, 58, 180), (253, 29, 29), (255, 255, 255)),
                ((34, 0, 80), (180, 0, 255), (255, 255, 255))],
    "gold":    [((20, 20, 30), (60, 50, 20), (255, 200, 60)),
                ((40, 30, 10), (90, 70, 20), (255, 215, 90))],
}


def _cycle(theme: str, i: int) -> tuple:
    pal = _THEMES[theme]
    return pal[i % len(pal)]


def _finalize(scenes: List[Scene]) -> None:
    for i, s in enumerate(scenes):
        s.index = i
        if s.seconds <= 0:
            s.seconds = _estimate_seconds(s.text)


def _topic(topic: str) -> str:
    return topic.strip().rstrip(".")


def _hashtags(lang: str, topic: str, kind: str) -> List[str]:
    tags = i18n.get(lang)["tags"]
    base = ["#" + "".join(w.capitalize() for w in topic.split()[:3])]
    return base + tags.get(kind, []) + tags["generic"]


# --- classic: hook -> points -> cta ----------------------------------------

def build_classic(topic: str, num_points: int, rng: random.Random, lang: str) -> Script:
    topic = _topic(topic)
    L = i18n.get(lang)
    hook = rng.choice(L["hooks"]).format(topic=topic)
    cta = rng.choice(L["ctas"]).format(topic=topic)
    points = rng.sample(L["points"], k=min(num_points, len(L["points"])))

    scenes = [Scene(0, "hook", hook, overlay=L["labels"]["wait"], palette=_cycle("sunset", 0))]
    for i, tmpl in enumerate(points, start=1):
        scenes.append(Scene(0, "point", tmpl.format(n=i, topic=topic),
                            overlay=f"#{i}", palette=_cycle("sunset", i)))
    scenes.append(Scene(0, "cta", cta, overlay=L["labels"]["follow"],
                        palette=_cycle("sunset", len(scenes))))
    _finalize(scenes)
    return Script(topic=topic, title=L["title"]["classic"].format(topic=topic.capitalize()),
                  template="classic", hashtags=_hashtags(lang, topic, "classic"),
                  scenes=scenes)


# --- quiz: intro -> (question, answer) pairs -> outro ----------------------

def build_quiz(topic: str, num_points: int, rng: random.Random, lang: str) -> Script:
    topic = _topic(topic)
    L = i18n.get(lang)
    scenes = [Scene(0, "intro", L["quiz_intro"].format(topic=topic),
                    overlay=L["labels"]["quiz"], palette=_cycle("ocean", 0))]
    qs = rng.sample(L["quiz_q"], k=min(num_points, len(L["quiz_q"])))
    ans = rng.sample(L["quiz_a"], k=min(num_points, len(L["quiz_a"])))
    for i in range(len(qs)):
        scenes.append(Scene(0, "question", qs[i].format(topic=topic),
                            overlay=f"{L['labels']['question'][0]}{i+1}",
                            palette=_cycle("ocean", 1)))
        scenes.append(Scene(0, "answer", ans[i].format(topic=topic),
                            overlay=L["labels"]["answer"], palette=_cycle("gold", i)))
    scenes.append(Scene(0, "outro", L["quiz_outro"].format(topic=topic),
                        overlay=L["labels"]["follow"], palette=_cycle("neon", 0)))
    _finalize(scenes)
    return Script(topic=topic, title=L["title"]["quiz"].format(topic=topic),
                  template="quiz", hashtags=_hashtags(lang, topic, "quiz"), scenes=scenes)


# --- top5: intro -> countdown ranks -> cta ---------------------------------

def build_top5(topic: str, num_points: int, rng: random.Random, lang: str) -> Script:
    topic = _topic(topic)
    L = i18n.get(lang)
    n = max(2, min(num_points, 5))
    scenes = [Scene(0, "intro", L["top_intro"].format(n=n, topic=topic),
                    overlay=f"{L['labels']['top']} {n}", palette=_cycle("neon", 1))]
    lines = rng.sample(L["rank_lines"], k=min(n, len(L["rank_lines"])))
    for rank in range(n, 0, -1):
        line = lines[(n - rank) % len(lines)]
        scenes.append(Scene(0, "rank", L["rank"].format(rank=rank, topic=topic, line=line),
                            overlay=f"#{rank}", palette=_cycle("sunset", rank)))
    scenes.append(Scene(0, "cta", L["top_cta"].format(topic=topic),
                        overlay=L["labels"]["save"], palette=_cycle("ocean", 0)))
    _finalize(scenes)
    return Script(topic=topic, title=L["title"]["top"].format(n=n, topic=topic),
                  template="top5", hashtags=_hashtags(lang, topic, "top"), scenes=scenes)


# --- storytelling: hook -> beats -> moral ----------------------------------

def build_story(topic: str, num_points: int, rng: random.Random, lang: str) -> Script:
    topic = _topic(topic)
    L = i18n.get(lang)
    themes = ["gold", "ocean", "neon", "sunset"]
    scenes = []
    for i, (kind, text, ov) in enumerate(L["story"]):
        scenes.append(Scene(0, kind, text.format(topic=topic), overlay=ov,
                            palette=_cycle(themes[i % len(themes)], i)))
    _finalize(scenes)
    return Script(topic=topic, title=L["title"]["story"].format(topic=topic),
                  template="storytelling", hashtags=_hashtags(lang, topic, "story"),
                  scenes=scenes)


TEMPLATES: Dict[str, Callable[[str, int, random.Random, str], Script]] = {
    "classic": build_classic,
    "quiz": build_quiz,
    "top5": build_top5,
    "storytelling": build_story,
}


def build_script(topic: str, template: str = "classic", num_points: int = 3,
                 seed: int | None = None, lang: str = "it") -> Script:
    if template not in TEMPLATES:
        raise ValueError(f"Template sconosciuto: {template}. "
                         f"Disponibili: {', '.join(TEMPLATES)}")
    rng = random.Random(seed)
    return TEMPLATES[template](topic, num_points, rng, lang)
