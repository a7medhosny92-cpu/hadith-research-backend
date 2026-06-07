"""Structural analysis of an isnad (chain of narrators).

We parse the chain into an ordered list of narrators by splitting on the classical
transmission terms (حدثنا، أخبرنا، عن، سمعت…), then flag features that matter to
hadith critics: the transmission mode of each link (سماع vs عنعنة), تحويل (ح) when
multiple chains merge, and whether the chain reaches the Prophet ﷺ.

This is a *structural* read, not an authenticity verdict: grading the narrators
themselves needs a rijal (narrator-biography) database — see the note in the
output. That database is the cat-26 corpus, a planned ingestion step.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from app.parsing.normalize import normalize_for_search, strip_diacritics
from app.rijal.graph import is_prophet

if TYPE_CHECKING:
    from app.rijal import RijalIndex, RijalMatch

# Transmission terms → mode. Keys are in the folded form of normalize_for_search.
_VIA: dict[str, str] = {
    "حدثنا": "سماع", "حدثني": "سماع", "حدثناه": "سماع", "ثنا": "سماع", "نا": "سماع",
    "اخبرنا": "سماع", "اخبرني": "سماع", "اخبرناه": "سماع", "انبانا": "سماع",
    "سمعت": "سماع", "سمعنا": "سماع", "سمع": "سماع", "سمعه": "سماع",
    "عن": "عنعنة", "عنه": "عنعنة",
}
# Connective words that are not narrator names.
_SKIP = {"قال", "قالا", "قالوا", "يعني", "قالت", "ح"}
# Matn-start markers: once the isnad reaches one of these (after a narrator) the matn
# has begun and the chain ends. «قال/قالت» are *soft* — a boundary only when NOT followed
# by a transmission verb (… قال حدثنا … keeps going); the rest always begin the matn.
_MATN_HARD = {"يقول", "تقول", "مرفوعا", "رفعه", "يرفعه", "نحوه", "مثله", "بنحوه", "بمثله", "فقال"}
_MATN_SOFT = {"قال", "قالت"}
# «أنّ / أنّه / أنّها» opens the report (matn) — «… عن ابن عمر أنّ رسول الله ﷺ قال …».
# If its subject is the Prophet the chain is marfūʿ and he is the terminal narrator;
# otherwise the report has begun and the chain ends. (Without this, «أن رسول الله» glued
# onto the previous name, making bogus nodes like «ابن عمر أن رسول الله ﷺ».)
_MATN_ANNA = {"ان", "انه", "انها"}
_PROPHET_HEAD = {"النبي", "نبي", "رسول"}
# Tokens still inside a Prophet reference (his name + the eulogy); the first token
# outside this set ends the Prophet's (terminal) name and starts the matn.
_EULOGY = {"النبي", "نبي", "رسول", "الله", "صلي", "عليه", "وسلم", "واله", "وصحبه", "سلم"}
_TOKEN = re.compile(r"[^\s،,.:؛()«»\"']+")


@dataclass(slots=True)
class Narrator:
    name: str
    via: str  # سماع | عنعنة | — (chain head)


@dataclass(slots=True)
class IsnadAnalysis:
    narrators: list[dict]
    length: int
    modes: dict[str, int]
    has_tahwil: bool          # ح — more than one route
    has_anana: bool           # عن — possible tadlīs, needs samāʿ confirmed
    reaches_prophet: bool
    notes: list[str]
    rijal_assessment: dict | None = None  # narrator gradings, when a RijalIndex is supplied

    def to_dict(self) -> dict:
        return asdict(self)


def _chain_assessment(matches: list["RijalMatch | None"], total: int) -> dict:
    """Summarise the chain from its narrator gradings — verdict by the weakest link."""
    ranks = [m.entry.rank for m in matches if m and m.entry.rank is not None]
    known = sum(1 for m in matches if m)
    unknown = total - known
    weakest = min(ranks) if ranks else None

    if weakest is None:
        verdict = "لم يُعرف رواة هذا الإسناد في قاعدة الرجال (القاعدة محدودة)."
    elif weakest <= 1:
        verdict = "في الإسناد راوٍ متروك أو متّهم؛ ضعيف جدًا."
    elif weakest == 2:
        verdict = "في الإسناد راوٍ ضعيف."
    elif weakest <= 4:
        verdict = "في الإسناد راوٍ مجهول أو ليّن الحديث."
    elif weakest <= 6:
        verdict = "في الإسناد من لا يُحتجّ بتفرّده (مقبول/صدوق له أوهام)."
    elif unknown == 0:
        verdict = "رجال الإسناد كلّهم ثقات أو أثبات بحسب القاعدة."
    else:
        verdict = f"مَن عُرف منهم ثقات؛ وبقي {unknown} راوٍ لم يُعرفوا في القاعدة."
    return {"weakest_rank": weakest, "known": known, "unknown": unknown, "verdict": verdict}


def analyze_isnad(text: str, rijal: "RijalIndex | None" = None) -> IsnadAnalysis:
    raw = strip_diacritics(text or "")
    narrators: list[Narrator] = []
    via: str | None = None
    buf: list[str] = []
    has_tahwil = False

    def flush() -> bool:
        name = " ".join(buf).strip(" -،")
        if name:
            narrators.append(Narrator(name=name, via=via or "—"))
            return is_prophet(name)   # the Prophet is terminal — nothing narrates from him
        return False

    tokens = _TOKEN.findall(raw)
    for i, token in enumerate(tokens):
        folded = normalize_for_search(token)
        nxt = normalize_for_search(tokens[i + 1]) if i + 1 < len(tokens) else ""
        if folded == "ح":
            has_tahwil = True  # تحويل: a standalone ح marks a route switch
            continue
        # accept a leading و (وحدثنا، وعن، وأخبرنا …)
        conn = folded if folded in _VIA else (
            folded[1:] if folded[:1] == "و" and folded[1:] in _VIA else None
        )
        if conn:
            if flush():           # reached the Prophet → stop; the matn follows
                break
            via, buf = _VIA[conn], []
            continue
        # «أنّ» opens the report: end the current narrator. If it is about the Prophet
        # («… أنّ رسول الله ﷺ قال») the chain is marfūʿ and he is the terminal narrator;
        # otherwise the report (matn) has begun → stop.
        if folded in _MATN_ANNA or (folded[:1] == "و" and folded[1:] in _MATN_ANNA):
            if flush():
                break
            if nxt in _PROPHET_HEAD:
                via, buf = None, []
                continue
            break
        # matn boundary: the isnad ends where the report (matn) begins
        nxt_is_via = nxt in _VIA or (nxt[:1] == "و" and nxt[1:] in _VIA)
        if folded in _MATN_HARD or (folded in _MATN_SOFT and not nxt_is_via):
            flush()
            break
        if folded in _MATN_SOFT:   # «قال حدثنا …» — connective, not the matn; drop it
            continue
        # the Prophet is the terminal narrator: once the buffer is the Prophet and the
        # next token isn't part of the eulogy, the matn has begun
        if buf and folded not in _EULOGY and is_prophet(" ".join(buf)):
            flush()
            break
        if folded in _SKIP:
            continue
        buf.append(token)
    else:
        flush()

    modes: dict[str, int] = {}
    for narrator in narrators:
        if narrator.via in ("سماع", "عنعنة"):
            modes[narrator.via] = modes.get(narrator.via, 0) + 1
    has_anana = modes.get("عنعنة", 0) > 0
    # marfūʿ iff the chain actually ends at the Prophet (not merely mentions him in matn)
    reaches_prophet = bool(narrators) and is_prophet(narrators[-1].name)

    narrator_dicts: list[dict] = []
    matches: list["RijalMatch | None"] = []
    for narrator in narrators:
        record = asdict(narrator)
        if rijal is not None:
            match = rijal.lookup(narrator.name)
            matches.append(match)
            record["rijal"] = match.to_dict() if match else None
        narrator_dicts.append(record)

    notes: list[str] = []
    if has_tahwil:
        notes.append("فيه تحويل (ح): أكثر من طريق في الإسناد.")
    if has_anana:
        notes.append("في الإسناد عنعنة؛ يُتحقَّق من ثبوت السماع (احتمال التدليس).")
    if len(narrators) < 3:
        notes.append("السند قصير؛ يُنظر في اتصاله.")

    if rijal is None:
        assessment = None
        notes.append("تقويم عدالة الرواة وضبطهم يتطلّب قاعدة بيانات الرجال (مرّر RijalIndex لتفعيله).")
    else:
        assessment = _chain_assessment(matches, len(narrators))
        notes.append("هذا حكمٌ على الرجال فقط؛ وصحّة الحديث تقتضي أيضًا اتصال السند وانتفاء العلّة والشذوذ.")

    return IsnadAnalysis(
        narrators=narrator_dicts,
        length=len(narrators),
        modes=modes,
        has_tahwil=has_tahwil,
        has_anana=has_anana,
        reaches_prophet=reaches_prophet,
        notes=notes,
        rijal_assessment=assessment,
    )


def continuity(narrators: list[dict], graph) -> dict:
    """Check each تلميذ→شيخ link against the narrator network: is the pair ever recorded
    together? A link never seen is a flag for a possible break (انقطاع) — a structural
    hint from the texts, not a verdict on سماع. ``graph`` is a NarratorGraph."""
    links = []
    for student, teacher in zip(narrators, narrators[1:]):
        weight = graph.link_weight(student["name"], teacher["name"])
        links.append(
            {"from": student["name"], "to": teacher["name"], "count": weight, "seen": weight > 0}
        )
    seen = sum(1 for link in links if link["seen"])
    if not links:
        note = "السند قصير؛ لا حلقات للمقابلة."
    elif seen == len(links):
        note = "كلّ حلقات الإسناد لها رواية معروفة في النصوص."
    else:
        note = (
            f"{len(links) - seen} من {len(links)} حلقة لم تُعرف روايتها في النصوص؛ "
            "يُنظر في الاتصال (قد يكون انقطاعًا أو اختلاف صيغة الاسم)."
        )
    return {"links": links, "seen": seen, "total": len(links), "note": note}


def overall_ruling(analysis: dict, continuity: dict | None = None) -> dict:
    """A single bottom-line «الحكم على الإسناد» that fuses the rijal verdict (by the
    weakest narrator), the اتصال check, and عنعنة.

    It is explicitly a verdict on the *apparent* state of the men and the connection —
    not a full تصحيح, which also needs النظر في العلّة والشذوذ. The narrator ranks come
    from ``app.rijal.grades.RANKS`` (10 = صحابي … 0 = كذاب). ``tone`` (sahih|hasan|daif|
    other) is for display colour. With a small rijal seed many narrators are unknown, so
    a positive verdict is held back to «يُتوقَّف فيه» until a fuller رجال base is loaded."""
    ra = analysis.get("rijal_assessment") or {}
    weakest = ra.get("weakest_rank")
    unknown = ra.get("unknown") or 0
    has_anana = bool(analysis.get("has_anana"))
    broken = bool(
        continuity and continuity.get("total")
        and continuity.get("seen", 0) < continuity["total"]
    )

    # 1) base verdict from the weakest *known* narrator
    if weakest is None:
        grade, tone, reason = (
            "غير محكوم عليه", "other", "لم يُعرف رواة هذا الإسناد في قاعدة الرجال"
        )
    elif weakest <= 1:        # كذاب / متروك
        grade, tone, reason = "ضعيف جدًا", "daif", "في الإسناد راوٍ متروك أو متّهم"
    elif weakest <= 3:        # ضعيف / مجهول
        grade, tone, reason = "ضعيف", "daif", "في الإسناد راوٍ ضعيف أو مجهول"
    elif weakest <= 6:        # لين / مقبول / صدوق له أوهام
        grade, tone, reason = (
            "حسن لغيره", "hasan",
            "في الإسناد مَن لا يُحتجّ بتفرّده؛ يُعتبر به في الشواهد والمتابعات",
        )
    elif weakest <= 8:        # صدوق
        grade, tone, reason = "حسن", "hasan", "أمثل رجاله صدوق؛ حديثه حسن لذاته"
    else:                     # ثقة / صحابي
        grade, tone, reason = "صحيح", "sahih", "رجاله كلّهم ثقات"

    # 2) narrators we couldn't find make a positive verdict non-final (the DB is limited)
    if unknown and tone in ("sahih", "hasan"):
        grade, tone = "يُتوقَّف فيه", "other"
        reason = f"{reason}؛ لكن بقي {unknown} راوٍ لم يُعرف في القاعدة فلا يُجزَم"

    # 3) a clear break in the chain weakens an otherwise sound isnad
    if broken and tone in ("sahih", "hasan", "other"):
        grade, tone = "ضعيف", "daif"
        reason = f"{reason}؛ وفي الإسناد انقطاعٌ ظاهر (حلقة غير معروفة في النصوص)"
    elif tone == "sahih" and continuity and continuity.get("total"):
        reason = f"{reason}؛ والإسناد متّصل بحسب الشبكة"

    # 4) عنعنة keeps a sound chain short of a firm تصحيح until السماع is confirmed
    if has_anana and tone == "sahih":
        grade = "صحيح إن ثبت السماع"
        reason = f"{reason}؛ وفيه عنعنة فيُتحقَّق من ثبوت السماع"

    return {
        "grade": grade,
        "tone": tone,
        "reason": reason,
        "disclaimer": (
            "حكمٌ على ظاهر حال الرجال واتصال السند فقط؛ وتمام التصحيح يقتضي النظر في "
            "العلّة والشذوذ. هذه أداة دراسة لا فتوى."
        ),
    }
