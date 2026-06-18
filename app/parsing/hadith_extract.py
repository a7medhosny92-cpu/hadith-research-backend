"""Extract structured hadith records from a downloaded turath book.

A book is a list of pages (``{"pg", "meta": {...}, "text"}``). Hadith are marked
inline; the marker style varies by edition, so we detect it per book:

* style **bullet** — ``• [N]``  (e.g. صحيح البخاري ط التأصيل)
* style **dash**   — ``N - …``  (صحيح مسلم، السنن، …)

A single hadith may span several pages, so we scan the page stream and accumulate
across page breaks, tracking the chapter (bab) heading and the starting page for
citation, and skipping the editor's muqaddima via the book ``numbers`` index.
"""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Pattern

from app.parsing.grading import extract_grade, grade_in_ruling
from app.parsing.html_clean import (
    arabic_digits_to_int,
    clean_block,
    clean_block_marked,
    extract_s0_grades,
    extract_titles,
    remove_footnote_refs,
    split_footnotes,
)
from app.parsing.isnad_matn import split_isnad_matn
from app.parsing.normalize import _DIACRITICS, _FOLD, normalize_for_search

_NUM = r"[\d٠-٩۰-۹]+"
# "• [N]" bullet (a "* [N]" line is a takhrij note, not a hadith — we anchor on •).
_MARKER_BULLET: Pattern[str] = re.compile(rf"(?:^|\n)[ \t]*•\s*\[\s*({_NUM})\s*\]")
# "N - " at the start of a line.
_MARKER_DASH: Pattern[str] = re.compile(rf"(?:^|\n)[ \t]*({_NUM})\s*-\s+")
# A leading sub-number like "(١)" some editions print after the hadith number.
_LEADING_SUBNUM = re.compile(rf"^\s*\(\s*{_NUM}\s*\)\s*")
_WS = re.compile(r"\s+")
# A dash marker «N - باب …» is a chapter heading printed as a numbered line in some
# editions, not a hadith — recognise it by its leading word so it isn't emitted.
_HEADING_WORDS = {"باب", "كتاب", "فصل", "جماع", "ابواب", "مقدمه"}
# A reference entry repeats the previous hadith's matn through a new chain. We match the
# reference word-forms ANYWHERE in the entry (not only its tail), so a «نحوه» that sits before
# an علّة note — «… عن النبي ﷺ نحوه. أبو حذيفة … كثير الوهم» — is still caught. Matched as token
# prefixes: نحوه/نحو ذلك · مثله/مثل ذلك · بنحوه/بمثله · بمعناه · بهذا الإسناد · بذلك.
_RIMANDO_RE = re.compile(r"^(?:ب?نحو|ب?مثل|بمعنا|بذلك|بهذا)")


@dataclass(slots=True)
class ParsedHadith:
    book_id: int
    number: int | None
    text: str            # full hadith text (isnad + matn), diacritics preserved
    isnad: str
    matn: str
    matn_confidence: str  # quote | phrase | none | ref | llm | taliq
    grade: str | None
    chapter: str | None
    volume: str | None
    page: int | None      # printed page (for citation)
    page_id: int | None   # turath sequential page id
    kind: str = "hadith"  # "hadith" (numbered) | "taliq" (a باب with only a تعليق/أثر, no numbered hadith)
    sort: int | None = None  # ordering key for a non-numbered «taliq» (the preceding hadith number)

    def to_dict(self) -> dict:
        return asdict(self)


def _finish(book_id: int, cur: dict, default_grade: str | None) -> ParsedHadith:
    text = _WS.sub(" ", " ".join(cur["parts"])).strip()
    isnad, matn, confidence = split_isnad_matn(text)
    grade = extract_grade(text) or grade_in_ruling(cur.get("grade_hint")) or default_grade
    return ParsedHadith(
        book_id=book_id,
        number=cur["number"],
        text=text,
        isnad=isnad,
        matn=matn,
        matn_confidence=confidence,
        grade=grade,
        chapter=cur["chapter"],
        volume=cur["volume"],
        page=cur["page"],
        page_id=cur["page_id"],
    )


_DASH_PROBE = re.compile(rf"(?:^|\n)[ \t]*{_NUM}\s*-\s")
_HEAD_NUM_PREFIX = re.compile(rf"^{_NUM}\s*-\s*")  # the «٢ - » before a باب title


def _fold_keep_pos(s: str) -> tuple[str, list[int]]:
    """Fold ``s`` like ``normalize_for_search`` (drop tashkeel/tatweel, unify alef/hamza/ta-marbuta)
    but KEEP a map from each folded-char index back to its raw index, so a match in the folded text
    maps back to a position in the raw block."""
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(s):
        if _DIACRITICS.match(ch) or ch == "ـ":
            continue
        for c in ch.translate(_FOLD):     # "" for a bare hamza, else one char
            out.append(c)
            idx.append(i)
    return "".join(out), idx


_HEAD_SENTINEL = "\x00"   # marks a title span's position in the cleaned block (clean_block_marked)


def _aligned(spans: list[str], titles: list[str]) -> bool:
    """The k-th title span on the page is the k-th indexed heading (same count, each text agreeing
    once folded and the «N - » number dropped) — so a sentinel can be mapped to a chapter by order."""
    if len(spans) != len(titles):
        return False
    for s, t in zip(spans, titles):
        a, b = _fold(_HEAD_NUM_PREFIX.sub("", s)), _fold(_HEAD_NUM_PREFIX.sub("", t))
        if not a or not b or (a not in b and b not in a):
            return False
    return True


def _fold(s: str) -> str:
    return _fold_keep_pos(s)[0]


def _locate_headings(block: str, page_heads: list[tuple[str, str]]) -> list[tuple[int, str]] | None:
    """Find each heading of the page INSIDE the block → ``[(raw_pos, chapter)]`` sorted by position.

    Several أبواب can share one page; the heading index gives their order but not where each sits in
    the text, so a hadith would be filed under the LAST باب of the page. Locating each title (folded
    for diacritics/orthography) lets every hadith take the باب that precedes it. Returns ``None`` —
    the caller then falls back to page-level assignment, no regression — when a title can't be located
    UNIQUELY (e.g. a bare «باب», or a title that also appears in a matn) or the positions aren't in
    heading order."""
    folded_block, idx = _fold_keep_pos(block)
    found: list[tuple[int, str]] = []
    for title, chapter in page_heads:
        pos = -1
        for key in (_fold_keep_pos(title)[0], _fold_keep_pos(_HEAD_NUM_PREFIX.sub("", title))[0]):
            if len(key) < 8:                              # too short to be distinctive (a bare «باب»)
                continue
            j = folded_block.find(key)
            if j != -1 and folded_block.find(key, j + 1) == -1:   # present and unique
                pos = idx[j]
                break
        if pos < 0:
            return None
        found.append((pos, chapter))
    if any(found[i][0] > found[i + 1][0] for i in range(len(found) - 1)):
        return None                                       # out of text order → fall back
    return found


def _detect_marker(pages: list[dict], start_page_id: int | None = None) -> Pattern[str]:
    """Pick the marker style for this book by comparing how often each style occurs.

    Sample **content** pages only: the editor's muqaddima often contains dash-style
    numbered lists ("٤ - …") that would otherwise mask the real "• [N]" markers.
    """
    content = [p for p in pages if start_page_id is None or p.get("pg", 0) >= start_page_id]
    text = "\n".join(p.get("text", "") for p in content[:50])
    bullets = text.count("• [")
    dashes = len(_DASH_PROBE.findall(text))
    return _MARKER_BULLET if bullets > 0 and bullets >= dashes else _MARKER_DASH


def iter_hadith(
    book_id: int,
    pages: Iterable[dict],
    *,
    default_grade: str | None = None,
    start_page_id: int | None = None,
    headings: list | None = None,
) -> Iterator[ParsedHadith]:
    """Yield :class:`ParsedHadith` for every hadith marker in the book.

    ``start_page_id`` skips front matter (the editor's muqaddima, which quotes hadith
    out of sequence): pass the page id where the real numbered text begins.

    ``headings`` (``indexes.headings`` — each a page-positioned {level, title}) builds a HIERARCHICAL
    chapter «كتاب ← باب», unique even when the باب title is just «بَابٌ» (untitled أبواب otherwise
    collide and fuse in the «الكتب» tab). Without it the chapter falls back to the page text.
    """
    pages = list(pages)
    pages_sorted = sorted(pages, key=lambda p: p.get("pg", 0))
    marker = _detect_marker(pages, start_page_id)
    current: dict | None = None
    chapter: str | None = None
    # Hierarchical chapter from indexes.headings: (page, level, title), sorted by page (stable → keeps
    # the array order within a page, so كتاب precedes its باب). `head_chapter[i]` is the full open
    # «كتاب ← باب» path after applying heading i (a higher level closes the deeper ones). A two-pointer
    # over the page stream then opens every heading whose page we've reached — robust when a heading's
    # page is NOT an exact page id (it opens on the next page, never silently dropped → no fusion;
    # mirrors sair_extract's page map).
    heads: list[tuple[int, int, str]] = []
    for h in (headings or []):
        p, t = h.get("page"), (h.get("title") or "").strip()
        if p is not None and t:
            heads.append((int(p), int(h.get("level") or 99), t))
    heads.sort(key=lambda x: x[0])
    head_chapter: list[str] = []
    _active: dict[int, str] = {}
    for _p, _lvl, _title in heads:
        for d in [l for l in list(_active) if l > _lvl]:
            del _active[d]
        _active[_lvl] = _title
        head_chapter.append(" ← ".join(_active[l] for l in sorted(_active)))
    heads_pages = [h[0] for h in heads]
    # Which heading-chapters actually got a numbered hadith, and the running max hadith number per page
    # (so a «taliq» باب — تعليق/أثر, no numbered hadith — can be ordered among the hadith afterwards).
    seen_chapters: set[str] = set()
    hadith_pages: list[int] = []
    hadith_numbers: list[int] = []

    for page in pages_sorted:
        pg = page.get("pg", 0)
        if start_page_id is not None and pg < start_page_id:
            continue
        meta = page.get("meta") or {}
        raw = page.get("text") or ""

        body, footnotes = split_footnotes(raw)
        page_grades = extract_s0_grades(footnotes) or extract_s0_grades(raw)
        # For a book WITH a headings index, keep each title span's POSITION (a sentinel) so several
        # أبواب on one page can be placed; otherwise (no index) fall back to the page-text chapter.
        if heads:
            block, span_titles = clean_block_marked(body, _HEAD_SENTINEL)
        else:
            block, span_titles = clean_block(body), []
            titles = extract_titles(body) or (meta.get("headings") or [])
            if titles:
                chapter = remove_footnote_refs(titles[-1]).strip()

        # Chapter from the headings index: `incoming` = the باب open before this page; the أبواب that
        # OPEN on this page are placed in the text (each hadith takes the باب that precedes it, not the
        # LAST of the page). `inpage` None → couldn't place them → fall back to the page-level باب.
        incoming = chapter
        inpage: list[tuple[int, str]] | None = None
        page_last = chapter
        if heads:
            lo = bisect.bisect_left(heads_pages, pg)
            hiq = bisect.bisect_right(heads_pages, pg)
            incoming = head_chapter[lo - 1] if lo > 0 else chapter
            page_last = head_chapter[hiq - 1] if hiq > 0 else chapter
            chapter = page_last or chapter
            if hiq > lo:
                sent = [i for i, c in enumerate(block) if c == _HEAD_SENTINEL]
                if sent and _aligned(span_titles, [heads[j][2] for j in range(lo, hiq)]):
                    inpage = [(sent[k], head_chapter[lo + k]) for k in range(hiq - lo)]   # spans → chapters
                elif not sent:   # plain-text headings (no spans) — locate the title in the block
                    inpage = _locate_headings(block, [(heads[j][2], head_chapter[j]) for j in range(lo, hiq)])

        def _chapter_at(pos: int) -> str | None:
            if inpage:
                ch = incoming
                for hpos, hch in inpage:
                    if hpos <= pos:
                        ch = hch
                    else:
                        break
                return ch
            return page_last if heads else chapter

        matches = list(marker.finditer(block))
        if not matches:
            if current is not None:
                current["parts"].append(block.replace(_HEAD_SENTINEL, " "))
            continue

        prefix = block[: matches[0].start()].replace(_HEAD_SENTINEL, " ")
        if current is not None and prefix.strip():
            current["parts"].append(prefix)

        for i, match in enumerate(matches):
            if current is not None:
                yield _finish(book_id, current, default_grade)
            end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
            grade_hint = page_grades[i] if i < len(page_grades) else None
            segment = _LEADING_SUBNUM.sub("", block[match.end():end].replace(_HEAD_SENTINEL, " "), count=1)
            head = normalize_for_search(segment[:40]).split()
            if head and head[0] in _HEADING_WORDS:   # a numbered «باب/كتاب …» heading, not a hadith
                if not heads:   # with the headings index the hierarchical chapter already covers it
                    chapter = remove_footnote_refs(segment.strip().split("\n", 1)[0]).strip() or chapter
                current = None
                continue
            number = arabic_digits_to_int(match.group(1))
            ch = _chapter_at(match.start())
            if ch:
                seen_chapters.add(ch)             # this باب has a numbered hadith → not a «taliq» باب
            if number is not None:
                hadith_pages.append(pg)
                hadith_numbers.append(number)
            current = {
                "number": number,
                "chapter": ch,
                "volume": meta.get("vol"),
                "page": meta.get("page"),
                "page_id": pg,
                "grade_hint": grade_hint,
                "parts": [segment],
            }

    if current is not None:
        yield _finish(book_id, current, default_grade)

    # ── post-pass: أبواب that carry only a تعليق / أثر (no numbered hadith) ─────────────────────────
    # The library groups by hadith, so a باب whose body is just a تعليق («وقال مالك: …») or an أثر —
    # very common in صحيح البخاري — never appears. Recover each as a «taliq» entry so the «الكتب» tab
    # shows the WHOLE book. They carry an empty isnad (the chain is مُعلّق) → the narrator graph and the
    # isnad audit skip them for free; kind="taliq" keeps them out of search and the matn audit.
    if heads:
        yield from _emit_taliq_sections(
            book_id, pages_sorted, heads, head_chapter, seen_chapters,
            hadith_pages, hadith_numbers, marker, start_page_id,
        )


def _meaningful_taliq(body: str) -> bool:
    """A real تعليق/أثر body (not an empty باب nor a stray fragment): ≥4 Arabic words."""
    return len([w for w in body.split() if any("ء" <= c <= "ي" for c in w)]) >= 4


def _emit_taliq_sections(
    book_id: int,
    pages_sorted: list[dict],
    heads: list[tuple[int, int, str]],
    head_chapter: list[str],
    seen_chapters: set[str],
    hadith_pages: list[int],
    hadith_numbers: list[int],
    marker: Pattern[str],
    start_page_id: int | None,
) -> Iterator[ParsedHadith]:
    """For every heading whose chapter got NO numbered hadith, recover its تعليق/أثر body.

    The body is the cleaned text of the heading's page range ``[page_i, page_{i+1})`` minus the
    heading line itself. A range that contains a hadith marker is skipped (a numbered hadith lives
    there → not a pure تعليق). Each emitted «taliq» is ordered (``sort``) right after the last hadith
    on an earlier page, so it sits in book order in the «الكتب» tab."""
    pg_clean: dict[int, str] = {}
    pg_meta: dict[int, dict] = {}
    pgs_list: list[int] = []
    for page in pages_sorted:
        pg = page.get("pg", 0)
        if start_page_id is not None and pg < start_page_id:
            continue
        body, _ = split_footnotes(page.get("text") or "")
        pg_clean[pg] = clean_block(body)
        pg_meta[pg] = page.get("meta") or {}
        pgs_list.append(pg)
    pgs_list.sort()

    # running max hadith number per page, so a taliq can be ordered among the numbered hadith
    order_pages: list[int] = []
    order_max: list[int] = []
    run = 0
    for pg, num in sorted(zip(hadith_pages, hadith_numbers)):
        run = max(run, num)
        order_pages.append(pg)
        order_max.append(run)

    def _sort_key(page_no: int) -> int:
        j = bisect.bisect_right(order_pages, page_no) - 1
        return order_max[j] if j >= 0 else 0

    # A كتاب that has بابs with hadith (e.g. «كتاب الإيمان», parent of «كتاب الإيمان ← باب النية») is an
    # ANCESTOR of a seen chapter — it is not itself a تعليق-only باب, so never emit it as one.
    ancestors: set[str] = set()
    for sc in seen_chapters:
        parts = sc.split(" ← ")
        for k in range(1, len(parts)):
            ancestors.add(" ← ".join(parts[:k]))

    for i, (p_i, _lvl, title) in enumerate(heads):
        cs = head_chapter[i]
        if cs in seen_chapters or cs in ancestors:   # has numbered hadith, or is a كتاب above ones that do
            continue
        p_next = next((heads[j][0] for j in range(i + 1, len(heads)) if heads[j][0] > p_i), None)
        lo = bisect.bisect_left(pgs_list, p_i)
        hi_ = bisect.bisect_left(pgs_list, p_next) if p_next is not None else len(pgs_list)
        rng = pgs_list[lo:hi_]
        if not rng:
            continue
        block = " ".join(pg_clean.get(pp, "") for pp in rng)
        if marker.search(block):                 # a numbered hadith sits here → not a pure تعليق range
            continue
        body = _WS.sub(" ", remove_footnote_refs(block).replace(title, " ", 1)).strip()
        if not _meaningful_taliq(body):
            continue
        meta = pg_meta.get(rng[0], {})
        yield ParsedHadith(
            book_id=book_id, number=None, text=body, isnad="", matn=body,
            matn_confidence="taliq", grade=None, chapter=cs,
            volume=meta.get("vol"), page=meta.get("page"), page_id=rng[0],
            kind="taliq", sort=_sort_key(p_i),
        )


def _first_text_page(data: dict) -> int | None:
    """Page id where the real numbered text starts, from the ``numbers`` index
    (hadith number → page id). Used to skip the editor's muqaddima."""
    numbers = (data.get("indexes") or {}).get("numbers") or {}
    pages = [int(v) for v in numbers.values() if str(v).lstrip("-").isdigit()]
    return min(pages) if pages else None


def _is_rimando(text: str) -> bool:
    """Does this entry refer back to the previous matn («مثله»/«نحوه»/«بهذا الإسناد»…)?"""
    return any(_RIMANDO_RE.match(tok) for tok in normalize_for_search(text).split())


def _inherit_rimandi(hadiths: list[ParsedHadith]) -> None:
    """In a book's reading order, an empty-matn reference entry («…مثله») carries the
    SAME text as the hadith it points back to — only the chain differs. Give it that
    matn (marked ``ref``) so the parallel narration is searchable, not blank."""
    last = ""
    for h in hadiths:
        if h.matn and h.matn.strip():
            last = h.matn
        elif last and _is_rimando(h.text):
            h.matn = last
            h.matn_confidence = "ref"


def parse_book_file(path: str | Path, *, default_grade: str | None = None,
                    llm_chains: dict | None = None) -> list[ParsedHadith]:
    """Parse a downloaded ``{raw_dir}/books/{id}.json`` file into hadith records.

    ``llm_chains`` (optional, from :func:`app.rijal.llm_source.load_llm_chains`) replaces the regex
    isnād/matn split with a faithful LLM re-segmentation for the chains the regex got wrong — gated,
    so without it the result is exactly the regex parse."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    hadiths = list(
        iter_hadith(
            int(data["book_id"]),
            data.get("pages", []),
            default_grade=default_grade,
            start_page_id=_first_text_page(data),
            headings=(data.get("indexes") or {}).get("headings"),
        )
    )
    _inherit_rimandi(hadiths)   # reference entries inherit the matn they point back to
    if llm_chains:
        import dataclasses
        from app.rijal.llm_source import text_key
        hadiths = [
            dataclasses.replace(h, isnad=seg["isnad"], matn=seg["matn"], matn_confidence="llm")
            if (seg := llm_chains.get(text_key(h.text))) else h
            for h in hadiths
        ]
    return hadiths
