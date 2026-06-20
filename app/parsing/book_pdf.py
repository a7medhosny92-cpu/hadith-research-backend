"""Render a downloaded turath book (its raw page TEXT) to a PDF, on demand, for the in-app reader.

The books are stored as structured page-text JSON (``data/raw/turath/books/{id}.json`` — `pages: [{pg,
text}]`), not as PDF. The «قراءة الكتب» tab reads a PAGE RANGE and serves it as a real PDF (Arabic RTL,
HarfBuzz-shaped, Noto Naskh) that the browser displays inline — so the big books (تاريخ الإسلام is 15,404
pages) are rendered a slice at a time, never whole.

fpdf2 + uharfbuzz are imported lazily, so the app runs without them; the reader endpoint reports clearly
if they are absent (install: ``pip install fpdf2 uharfbuzz``).
"""

from __future__ import annotations

from app.parsing.html_clean import clean_block

NASKH = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
NASKH_B = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"
_GREEN = (31, 122, 82)
_MUTED = (120, 110, 88)
_INK = (38, 34, 28)
_LINE = (210, 198, 170)


class _MissingDeps(RuntimeError):
    """Raised when fpdf2 / uharfbuzz are not installed."""


def _font_path() -> str:
    """The Noto Naskh path — or raise if the font isn't present."""
    import os
    for p in (NASKH, "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"):
        if os.path.exists(p):
            return p
    raise _MissingDeps("Noto Naskh Arabic font not found")


def render_book_pdf(title: str, pages: list[dict], *, start: int, count: int) -> bytes:
    """Render book ``pages`` whose ``pg`` ∈ [start, start+count) to PDF bytes (Arabic RTL).

    Each book page is a «صفحة N» divider + its cleaned text; long pages flow across PDF pages, and the
    book title rides every page header. Raises :class:`_MissingDeps` if fpdf2/uharfbuzz are unavailable."""
    try:
        from fpdf import FPDF
    except ImportError as exc:  # pragma: no cover - import guard
        raise _MissingDeps("fpdf2 is required for the book reader — pip install fpdf2 uharfbuzz") from exc

    font = _font_path()
    bold = NASKH_B if __import__("os").path.exists(NASKH_B) else font
    sel = [p for p in pages if start <= (p.get("pg") or 0) < start + count]

    class Reader(FPDF):
        def header(self) -> None:
            self.set_font("n", "B", 9.5)
            self.set_text_color(*_MUTED)
            self.cell(0, 7, title, align="R")
            self.set_draw_color(*_LINE)
            self.set_line_width(0.3)
            self.line(16, 21, self.w - 16, 21)
            self.set_y(25)

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("n", "", 8.5)
            self.set_text_color(*_MUTED)
            self.cell(0, 8, str(self.page_no()), align="C")

    pdf = Reader(format="A4")
    pdf.add_font("n", "", font)
    pdf.add_font("n", "B", bold)
    try:
        pdf.set_text_shaping(True)
    except Exception as exc:  # pragma: no cover - uharfbuzz guard
        raise _MissingDeps("uharfbuzz is required for Arabic shaping — pip install uharfbuzz") from exc
    pdf.set_margins(16, 14, 16)
    pdf.set_auto_page_break(True, margin=16)

    if not sel:
        pdf.add_page()
        pdf.set_font("n", "", 13)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(0, 9, "لا صفحاتٌ في هذا النطاق.", align="C")
        return bytes(pdf.output())

    for p in sel:
        pdf.add_page()
        pdf.set_font("n", "B", 10.5)
        pdf.set_text_color(*_GREEN)
        pdf.cell(0, 8, f"صفحة {p.get('pg')}", align="C")
        pdf.ln(10)
        pdf.set_font("n", "", 12.5)
        pdf.set_text_color(*_INK)
        text = clean_block(p.get("text") or "").strip() or "(صفحةٌ فارغة)"
        pdf.multi_cell(0, 7.8, text, align="R")
    return bytes(pdf.output())
