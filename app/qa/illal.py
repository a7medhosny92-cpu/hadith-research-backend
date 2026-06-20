"""Structural عِلّة / شذوذ signals from the gathered طرق (ROADMAP #7).

Beyond the STATED defects (``rulings.extract_illal`` — «أعلّه فلان، الصواب وقفه…»), this DETECTS
candidate defects by comparing the parallel narrations التخريج already gathered for a report:

* **غرابة / تفرّد** — it comes back to a single Companion, or has no متابع at all in the corpus.
* **شذوذ في المتن** — a lone wording (one route, «بمعناه») against a well-attested one (the many).
* **اضطراب** — heavy wording-disagreement from ONE مخرج with no راجح lafẓ.
* **اختلاف الرفع والوقف** — the routes split on reaching the Prophet ﷺ (a classic علّة).
* **اختلاف الوصل والإرسال** — among the مرفوع routes, some are موصولة (a صحابيّ heard the Prophet ﷺ) and
  some مرسلة (a تابعيّ attributes to him with no صحابيّ) — the زيادة (the وصل) is weighed, a classic علّة.

Every signal is a **HINT to investigate** («يُحتمل / يُنظر»), NEVER a verdict — favouring few correct
flags over many noisy ones (the روادك «التخريج» already gives the routes; we only read their shape).
Consumes the dict :func:`app.qa.takhrij.analyze_narrations` returns.
"""

from __future__ import annotations

from app.qa.isnad import analyze_isnad


def detect_structural_illal(takhrij: dict, *, check_raf_waqf: bool = True) -> list[dict]:
    """Return a list of structural عِلّة/شذوذ HINTS — ``{type, severity, note}`` — read from the shape
    of the gathered طرق. ``severity`` ∈ ``info`` (a note) / ``warn`` (a likely defect to weigh).
    ``check_raf_waqf=False`` skips the per-route مرفوع/موقوف pass (which parses each chain)."""
    groups = takhrij.get("groups", []) or []
    total = takhrij.get("total", 0)
    companions = takhrij.get("companions", 0)
    named = [g for g in groups if g.get("companion")]
    hints: list[dict] = []

    # 1) غرابة / تفرّد — how many independent مخارج carry it.
    if total == 0:
        hints.append({"type": "تفرّد", "severity": "info",
                      "note": "لم نقف له على متابعٍ في القاعدة — غريبٌ بهذا اللفظ (وقد تكون له طرقٌ خارجها)."})
    elif companions == 1 and named:
        hints.append({"type": "تفرّد", "severity": "info",
                      "note": f"تفرّد به الصحابيُّ {named[0]['companion']} — لم يروه عنه ﷺ في القاعدة "
                              f"صحابيٌّ غيره؛ يُنظر في تفرّده."})

    # 2) شذوذ في المتن — a lone wording (one route, «بمعناه») against a well-attested one (≥3) from the
    #    SAME Companion: the odd wording may be a راوٍ's error (مخالفة الأوثق/الأكثر).
    for g in named:
        variants = g.get("variants", []) or []
        if len(variants) < 2:
            continue
        dominant = max((v.get("count", 0) for v in variants), default=0)
        if dominant >= 3 and any(v.get("count") == 1 and v.get("label") == "بمعناه" for v in variants):
            hints.append({"type": "شذوذ", "severity": "warn",
                          "note": f"لفظٌ تفرّد به راوٍ عن {g['companion']} يخالف روايةَ الأكثر "
                                  f"({dominant} طرق متقاربة) — يُنظر في شذوذه."})

    # 3) اضطراب — ≥3 wordings from one مخرج, none close to the source (all «بمعناه»): no راجح lafẓ.
    for g in named:
        variants = g.get("variants", []) or []
        if len(variants) >= 3 and all(v.get("label") == "بمعناه" for v in variants):
            hints.append({"type": "اضطراب", "severity": "info",
                          "note": f"اختلافٌ كثيرٌ في اللفظ عن {g['companion']} ({len(variants)} صيغ) "
                                  f"دون لفظٍ راجح — يُحتمل الاضطراب."})

    # 4 & 5) per-route structural pass — parse each chain ONCE (analyze_isnad), reading two splits:
    #    رفع/وقف (does it reach the Prophet ﷺ) and, among the مرفوع, وصل/إرسال (a صحابيّ heard him, vs a
    #    تابعيّ attributing with no صحابيّ). Conservative: ≥2 on the minority side, so a single mis-parse
    #    or one unidentified terminal never flags.
    if check_raf_waqf:
        routes = [n for g in groups for v in (g.get("variants", []) or []) for n in (v.get("narrations", []) or [])]
        if len(routes) >= 4:
            marfu = mawquf = mawsul = mursal = 0
            for n in routes:
                text = f"{n.get('isnad', '') or ''} {n.get('matn', '') or ''}".strip()
                if not text:
                    continue
                analysis = analyze_isnad(text)
                if not analysis.reaches_prophet:
                    mawquf += 1
                    continue
                marfu += 1
                humans = [x for x in analysis.narrators if not x.get("is_prophet")]
                terminal = humans[-1] if humans else {}      # the last HUMAN before the Prophet ﷺ node
                grade = (terminal.get("rijal") or {}).get("grade")
                if grade == "صحابي":
                    mawsul += 1                       # a Companion heard the Prophet ﷺ → موصول
                elif grade:                           # a CONFIDENT non-Companion terminal reaching him → مرسل
                    mursal += 1                       # (an unidentified terminal is counted as neither)
            if min(marfu, mawquf) >= 2:
                hints.append({"type": "رفع ووقف", "severity": "warn",
                              "note": f"اختلفت الطرق في الرفع والوقف ({marfu} مرفوعة · {mawquf} موقوفة/مقطوعة) "
                                      f"— علّةٌ محتملة يُرجَّح بينها."})
            if min(mawsul, mursal) >= 2:
                hints.append({"type": "وصل وإرسال", "severity": "warn",
                              "note": f"اختلفت الطرق في الوصل والإرسال ({mawsul} موصولة بصحابيّ · {mursal} مرسلة عن "
                                      f"تابعيّ) — علّةٌ محتملة، فوصلُها زيادةٌ يُنظَر في ثبوتها أمام مَن أرسلها."})
    return hints
