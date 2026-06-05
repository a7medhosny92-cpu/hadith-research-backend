"""Language packs for script generation.

Each supported language provides the phrase banks and on-screen labels used by
the templates, so the whole video (script + captions + hashtags) is produced in
the chosen language. Unknown languages fall back to English.

Add a language by copying a block and translating the strings.
"""

from __future__ import annotations

import re
from typing import Dict, List

# Arabic diacritics (harakat/tanwin/shadda/sukun, superscript alef, tatweel...).
_TASHKEEL = re.compile(
    "[ؐ-ًؚ-ٰٟۖ-ۜ۟-ۤ"
    "۪ۧۨ-ۭـ]")


def strip_tashkeel(s: str) -> str:
    """Remove Arabic diacritics so the on-screen caption stays clean.

    The diacritized form is kept only for TTS, where it drives correct
    pronunciation; the display caption uses the bare letters.
    """
    return _TASHKEEL.sub("", s)


# Languages that have a full content pack here.
SUPPORTED = ("it", "en", "es", "ar")

# Right-to-left languages (need reshaping + bidi when rendering).
RTL = ("ar",)


def is_rtl(lang: str) -> bool:
    return lang in RTL


def get(lang: str) -> dict:
    return _PACKS.get(lang, _PACKS["en"])


def is_supported(lang: str) -> bool:
    return lang in _PACKS


_PACKS: Dict[str, dict] = {
    # ---------------------------------------------------------------- Italian
    "it": {
        "labels": {"wait": "ASPETTA...", "follow": "SEGUIMI", "answer": "RISPOSTA",
                   "quiz": "QUIZ", "save": "SALVA", "story": "STORIA", "top": "TOP",
                   "question": "DOMANDA"},
        "title": {
            "classic": "{topic}: quello che devi sapere",
            "quiz": "Quiz: {topic}",
            "top": "Top {n}: {topic}",
            "story": "La storia di {topic}",
        },
        "hooks": [
            "Nessuno ti ha mai spiegato questo su {topic}.",
            "Sto per cambiarti il modo di vedere {topic}.",
            "3 cose su {topic} che ti faranno dire 'wow'.",
            "Il segreto su {topic} che gli esperti non dicono.",
        ],
        "ctas": [
            "Salva questo video e seguimi per altro su {topic}.",
            "Quale ti ha sorpreso di piu'? Scrivilo nei commenti.",
            "Condividilo con chi deve sapere questo su {topic}.",
        ],
        "points": [
            "Punto {n}: {topic} funziona meglio quando parti dalle basi.",
            "Punto {n}: quasi tutti ignorano questo dettaglio su {topic}.",
            "Punto {n}: un piccolo cambiamento qui fa una differenza enorme.",
            "Punto {n}: ecco l'errore numero uno da evitare con {topic}.",
            "Punto {n}: prova questo per 7 giorni e vedrai i risultati.",
        ],
        "quiz_intro": "Quiz lampo su {topic}. Quanti ne indovini?",
        "quiz_q": [
            "Sai davvero questo su {topic}?",
            "Domanda: cosa succede con {topic}?",
            "Indovina: qual e' la verita' su {topic}?",
        ],
        "quiz_a": [
            "La risposta e' piu' semplice di quanto pensi: parti dalle basi.",
            "Esatto: la maggior parte delle persone sbaglia proprio qui.",
            "Sorpresa: e' l'opposto di quello che credevi.",
        ],
        "quiz_outro": "Quanti ne hai indovinati su {topic}? Scrivilo e seguimi!",
        "top_intro": "I {n} migliori trucchi su {topic}. Il numero 1 ti sorprendera'.",
        "rank": "Numero {rank}: un consiglio su {topic} {line}",
        "rank_lines": [
            "perche' fa davvero la differenza ogni giorno.",
            "e quasi nessuno lo sfrutta come dovrebbe.",
            "che cambia tutto se lo applichi subito.",
            "il segreto che gli esperti tengono per se'.",
        ],
        "top_cta": "Quale useresti per primo? Salva il video e seguimi per altri su {topic}.",
        "story": [
            ("hook", "Ti racconto una storia su {topic} che cambia tutto.", "STORIA"),
            ("beat", "All'inizio con {topic} sembrava tutto semplice.", "1"),
            ("beat", "Poi e' arrivato il problema che nessuno si aspettava.", "2"),
            ("beat", "La svolta e' stata capire una cosa su {topic}.", "3"),
            ("beat", "Da quel momento e' cambiato tutto, in meglio.", "4"),
            ("cta", "La morale? Non mollare con {topic}. Seguimi per la parte 2.", "SEGUIMI"),
        ],
        "tags": {"generic": ["#perte", "#fyp", "#viral"],
                 "classic": ["#imparacon"], "quiz": ["#quiz", "#indovina"],
                 "top": ["#classifica"], "story": ["#storytime", "#storia"]},
    },
    # ---------------------------------------------------------------- English
    "en": {
        "labels": {"wait": "WAIT...", "follow": "FOLLOW", "answer": "ANSWER",
                   "quiz": "QUIZ", "save": "SAVE", "story": "STORY", "top": "TOP",
                   "question": "QUESTION"},
        "title": {
            "classic": "{topic}: what you need to know",
            "quiz": "Quiz: {topic}",
            "top": "Top {n}: {topic}",
            "story": "The story of {topic}",
        },
        "hooks": [
            "Nobody ever explained this about {topic}.",
            "I'm about to change how you see {topic}.",
            "3 things about {topic} that will blow your mind.",
            "The secret about {topic} the experts won't tell you.",
        ],
        "ctas": [
            "Save this video and follow me for more on {topic}.",
            "Which one surprised you most? Tell me in the comments.",
            "Share it with someone who needs to know this about {topic}.",
        ],
        "points": [
            "Point {n}: {topic} works best when you start with the basics.",
            "Point {n}: almost everyone ignores this detail about {topic}.",
            "Point {n}: one small change here makes a huge difference.",
            "Point {n}: here's the number one mistake to avoid with {topic}.",
            "Point {n}: try this for 7 days and you'll see the results.",
        ],
        "quiz_intro": "Quick quiz on {topic}. How many can you guess?",
        "quiz_q": [
            "Do you really know this about {topic}?",
            "Question: what happens with {topic}?",
            "Guess: what's the truth about {topic}?",
        ],
        "quiz_a": [
            "The answer is simpler than you think: start with the basics.",
            "Exactly: most people get it wrong right here.",
            "Surprise: it's the opposite of what you believed.",
        ],
        "quiz_outro": "How many did you get right about {topic}? Comment and follow me!",
        "top_intro": "The {n} best tips about {topic}. Number 1 will surprise you.",
        "rank": "Number {rank}: a tip about {topic} {line}",
        "rank_lines": [
            "because it truly makes a difference every day.",
            "and almost nobody uses it the right way.",
            "that changes everything if you apply it now.",
            "the secret the experts keep to themselves.",
        ],
        "top_cta": "Which would you try first? Save the video and follow me for more on {topic}.",
        "story": [
            ("hook", "Let me tell you a story about {topic} that changes everything.", "STORY"),
            ("beat", "At first, {topic} seemed simple.", "1"),
            ("beat", "Then came the problem nobody expected.", "2"),
            ("beat", "The turning point was understanding one thing about {topic}.", "3"),
            ("beat", "From that moment, everything changed for the better.", "4"),
            ("cta", "The moral? Don't give up on {topic}. Follow me for part 2.", "FOLLOW"),
        ],
        "tags": {"generic": ["#foryou", "#fyp", "#viral"],
                 "classic": ["#learnwith"], "quiz": ["#quiz", "#guess"],
                 "top": ["#ranking"], "story": ["#storytime", "#story"]},
    },
    # ---------------------------------------------------------------- Spanish
    "es": {
        "labels": {"wait": "ESPERA...", "follow": "SÍGUEME", "answer": "RESPUESTA",
                   "quiz": "QUIZ", "save": "GUARDA", "story": "HISTORIA", "top": "TOP",
                   "question": "PREGUNTA"},
        "title": {
            "classic": "{topic}: lo que debes saber",
            "quiz": "Quiz: {topic}",
            "top": "Top {n}: {topic}",
            "story": "La historia de {topic}",
        },
        "hooks": [
            "Nadie te ha explicado esto sobre {topic}.",
            "Voy a cambiar tu forma de ver {topic}.",
            "3 cosas sobre {topic} que te dejaran sin palabras.",
            "El secreto sobre {topic} que los expertos no cuentan.",
        ],
        "ctas": [
            "Guarda este video y sigueme para mas sobre {topic}.",
            "Cual te sorprendio mas? Dimelo en los comentarios.",
            "Compartelo con quien deba saber esto sobre {topic}.",
        ],
        "points": [
            "Punto {n}: {topic} funciona mejor si empiezas por lo basico.",
            "Punto {n}: casi todos ignoran este detalle sobre {topic}.",
            "Punto {n}: un pequeno cambio aqui marca una gran diferencia.",
            "Punto {n}: este es el error numero uno que evitar con {topic}.",
            "Punto {n}: prueba esto 7 dias y veras los resultados.",
        ],
        "quiz_intro": "Quiz rapido sobre {topic}. Cuantas aciertas?",
        "quiz_q": [
            "De verdad sabes esto sobre {topic}?",
            "Pregunta: que pasa con {topic}?",
            "Adivina: cual es la verdad sobre {topic}?",
        ],
        "quiz_a": [
            "La respuesta es mas simple de lo que crees: empieza por lo basico.",
            "Exacto: la mayoria se equivoca justo aqui.",
            "Sorpresa: es lo contrario de lo que creias.",
        ],
        "quiz_outro": "Cuantas acertaste sobre {topic}? Comenta y sigueme!",
        "top_intro": "Los {n} mejores trucos sobre {topic}. El numero 1 te sorprendera.",
        "rank": "Numero {rank}: un consejo sobre {topic} {line}",
        "rank_lines": [
            "porque marca la diferencia cada dia.",
            "y casi nadie lo aprovecha bien.",
            "que lo cambia todo si lo aplicas ya.",
            "el secreto que los expertos guardan.",
        ],
        "top_cta": "Cual usarias primero? Guarda el video y sigueme para mas sobre {topic}.",
        "story": [
            ("hook", "Te cuento una historia sobre {topic} que lo cambia todo.", "HISTORIA"),
            ("beat", "Al principio con {topic} todo parecia simple.", "1"),
            ("beat", "Luego llego el problema que nadie esperaba.", "2"),
            ("beat", "El giro fue entender una cosa sobre {topic}.", "3"),
            ("beat", "Desde ese momento todo cambio, para mejor.", "4"),
            ("cta", "La moraleja? No te rindas con {topic}. Sigueme para la parte 2.", "SÍGUEME"),
        ],
        "tags": {"generic": ["#parati", "#fyp", "#viral"],
                 "classic": ["#aprendecon"], "quiz": ["#quiz", "#adivina"],
                 "top": ["#ranking"], "story": ["#storytime", "#historia"]},
    },
    # ----------------------------------------------------------------- Arabic
    "ar": {
        "labels": {"wait": "انتظر...", "follow": "تابعني", "answer": "الإجابة",
                   "quiz": "اختبار", "save": "احفظ", "story": "قصة", "top": "أفضل",
                   "question": "سؤال"},
        "title": {
            "classic": "{topic}: ما يجب أن تعرفه",
            "quiz": "اختبار: {topic}",
            "top": "أفضل {n}: {topic}",
            "story": "قصة {topic}",
        },
        # Spoken text is diacritized (tashkeel) for correct TTS pronunciation;
        # the on-screen caption strips it back to clean letters automatically.
        "hooks": [
            "لَمْ يَشْرَحْ لَكَ أَحَدٌ هٰذَا عَنْ {topic}.",
            "سَأُغَيِّرُ نَظْرَتَكَ إِلَى {topic}.",
            "ثَلَاثَةُ أَشْيَاءَ عَنْ {topic} سَتُذْهِلُكَ.",
            "السِّرُّ فِي {topic} الَّذِي لَا يُخْبِرُكَ بِهِ الْخُبَرَاءُ.",
        ],
        "ctas": [
            "اِحْفَظْ هٰذَا الْفِيدِيُو وَتَابِعْنِي لِلْمَزِيدِ عَنْ {topic}.",
            "أَيُّهَا فَاجَأَكَ أَكْثَرَ؟ اُكْتُبْ فِي التَّعْلِيقَاتِ.",
            "شَارِكْهُ مَعَ مَنْ يَجِبُ أَنْ يَعْرِفَ هٰذَا عَنْ {topic}.",
        ],
        "points": [
            "النُّقْطَةُ {n}: اِبْدَأْ دَائِمًا بِالْأَسَاسِيَّاتِ فِي {topic}.",
            "النُّقْطَةُ {n}: مُعْظَمُ النَّاسِ يَتَجَاهَلُونَ هٰذِهِ التَّفْصِيلَةَ عَنْ {topic}.",
            "النُّقْطَةُ {n}: تَغْيِيرٌ صَغِيرٌ هُنَا يُحْدِثُ فَرْقًا كَبِيرًا.",
            "النُّقْطَةُ {n}: هٰذَا هُوَ الْخَطَأُ الْأَوَّلُ الَّذِي يَجِبُ تَجَنُّبُهُ مَعَ {topic}.",
            "النُّقْطَةُ {n}: جَرِّبْ هٰذَا لِسَبْعَةِ أَيَّامٍ وَسَتَرَى النَّتَائِجَ.",
        ],
        "quiz_intro": "اِخْتِبَارٌ سَرِيعٌ عَنْ {topic}. كَمْ سَتُصِيبُ؟",
        "quiz_q": [
            "هَلْ تَعْرِفُ حَقًّا هٰذَا عَنْ {topic}؟",
            "سُؤَالٌ: مَاذَا يَحْدُثُ مَعَ {topic}؟",
            "خَمِّنْ: مَا الْحَقِيقَةُ عَنْ {topic}؟",
        ],
        "quiz_a": [
            "الْإِجَابَةُ أَبْسَطُ مِمَّا تَظُنُّ: اِبْدَأْ بِالْأَسَاسِيَّاتِ.",
            "بِالضَّبْطِ: مُعْظَمُ النَّاسِ يُخْطِئُونَ هُنَا تَمَامًا.",
            "مُفَاجَأَةٌ: إِنَّهُ عَكْسُ مَا كُنْتَ تَظُنُّ.",
        ],
        "quiz_outro": "كَمْ أَصَبْتَ عَنْ {topic}؟ اُكْتُبْ وَتَابِعْنِي!",
        "top_intro": "أَفْضَلُ {n} نَصَائِحَ عَنْ {topic}. الرَّقْمُ وَاحِدٌ سَيُفَاجِئُكَ.",
        "rank": "رَقْمُ {rank}: نَصِيحَةٌ عَنْ {topic} {line}",
        "rank_lines": [
            "لِأَنَّهَا تُحْدِثُ فَرْقًا كُلَّ يَوْمٍ.",
            "وَقِلَّةٌ مَنْ يَسْتَغِلُّهَا بِشَكْلٍ صَحِيحٍ.",
            "تُغَيِّرُ كُلَّ شَيْءٍ إِذَا طَبَّقْتَهَا الْآنَ.",
            "السِّرُّ الَّذِي يَحْتَفِظُ بِهِ الْخُبَرَاءُ.",
        ],
        "top_cta": "أَيُّهَا سَتُجَرِّبُ أَوَّلًا؟ اِحْفَظِ الْفِيدِيُو وَتَابِعْنِي لِلْمَزِيدِ عَنْ {topic}.",
        "story": [
            ("hook", "سَأَحْكِي لَكَ قِصَّةً عَنْ {topic} تُغَيِّرُ كُلَّ شَيْءٍ.", "قصة"),
            ("beat", "فِي الْبِدَايَةِ بَدَا كُلُّ شَيْءٍ بَسِيطًا مَعَ {topic}.", "١"),
            ("beat", "ثُمَّ جَاءَتِ الْمُشْكِلَةُ الَّتِي لَمْ يَتَوَقَّعْهَا أَحَدٌ.", "٢"),
            ("beat", "نُقْطَةُ التَّحَوُّلِ كَانَتْ فَهْمَ شَيْءٍ عَنْ {topic}.", "٣"),
            ("beat", "مِنْ تِلْكَ اللَّحْظَةِ تَغَيَّرَ كُلُّ شَيْءٍ لِلْأَفْضَلِ.", "٤"),
            ("cta", "الْعِبْرَةُ؟ لَا تَسْتَسْلِمْ مَعَ {topic}. تَابِعْنِي لِلْجُزْءِ الثَّانِي.", "تابعني"),
        ],
        "tags": {"generic": ["#لك", "#اكسبلور", "#فيرال"],
                 "classic": ["#تعلم"], "quiz": ["#اختبار", "#خمن"],
                 "top": ["#ترتيب"], "story": ["#قصة", "#حكاية"]},
    },
}
