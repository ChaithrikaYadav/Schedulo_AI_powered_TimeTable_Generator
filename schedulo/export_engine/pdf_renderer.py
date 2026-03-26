"""
schedulo/export_engine/pdf_renderer.py
ReportLab PDF renderer for Schedulo timetables.

Produces an A3-landscape PDF with one page per section,
styled to match the aSc timetable visual look:
  - Colour-coded cells by slot type
  - Section + department in page header
  - Period/day grid with wrapped text in cells
  - Page footer with generation timestamp
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── ReportLab colours (R, G, B in 0-1 range) ──────────────────────
def _rgb(hex_str: str):
    """Convert RRGGBB hex string to reportlab Color."""
    from reportlab.lib.colors import HexColor
    return HexColor(f"#{hex_str}")

TYPE_COLOUR = {
    "Theory":   "DCE6F1",
    "Lab":      "D9EAD3",
    "Lab_Cont": "BDD7EE",
    "Lunch":    "FFEB9C",
    "Free":     "EEECE1",
    "Project":  "E2EFDA",
}
HEADER_COLOUR = "4472C4"
HEADER_TEXT_COLOUR = "FFFFFF"
BORDER_COLOUR = "999999"

# Page geometry (A3 landscape)
PAGE_WIDTH_PT = 1191.0   # A3 landscape width in points
PAGE_HEIGHT_PT = 842.0
MARGIN = 36.0            # 0.5 inch
CELL_HEIGHT = 80.0


class PDFRenderer:
    """
    Renders Schedulo section timetables to a multi-page A3 PDF.

    Usage:
        renderer = PDFRenderer()
        buf = renderer.render_from_dataframes(section_dfs, department="CSE")
        with open("timetable.pdf", "wb") as f:
            f.write(buf.read())
    """

    def render_from_dataframes(
        self,
        section_dfs: dict[str, pd.DataFrame],
        department: str = "University Timetable",
        academic_year: str = "2024-25",
    ) -> io.BytesIO:
        """
        Render all sections to PDF pages.

        Args:
            section_dfs: {section_id → DataFrame(rows=Days, cols=Periods)}
            department:  Label printed in page header
            academic_year: Label printed in page header

        Returns:
            BytesIO containing PDF bytes
        """
        try:
            from reportlab.lib.pagesizes import A3, landscape
            from reportlab.lib.units import cm, pt
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.colors import HexColor, black, white
        except ImportError:
            logger.warning("reportlab not installed — returning empty PDF stub")
            return self._stub_pdf()

        buf = io.BytesIO()
        canv = rl_canvas.Canvas(buf, pagesize=landscape(A3))
        page_w, page_h = landscape(A3)
        styles = self._get_styles()
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        for section_id, df in section_dfs.items():
            logger.info(f"PDFRenderer: rendering section {section_id}")
            self._render_section_page(
                canv, df, section_id, department, academic_year,
                page_w, page_h, now_str,
            )
            canv.showPage()

        canv.save()
        buf.seek(0)
        logger.info(f"PDF rendered: {len(section_dfs)} sections")
        return buf

    async def render_from_db(
        self,
        timetable_id: int,
        db: Any,
        department: str = "",
        academic_year: str = "2024-25",
    ) -> io.BytesIO:
        """Load slots from DB and render to PDF."""
        from sqlalchemy import select
        from schedulo.models import TimetableSlot, Section, Timetable
        from collections import defaultdict
        from schedulo.scheduler_core.prototype_scheduler import PERIODS, DAYS

        tt_res = await db.execute(select(Timetable).where(Timetable.id == timetable_id))
        tt = tt_res.scalar_one_or_none()
        department = department or (tt.department if tt else "University")
        academic_year = academic_year or (tt.academic_year if tt else "2024-25")

        result = await db.execute(
            select(TimetableSlot).where(TimetableSlot.timetable_id == timetable_id)
        )
        slots = result.scalars().all()

        sec_result = await db.execute(select(Section))
        sections = {str(s.id): s.section_id for s in sec_result.scalars().all()}

        section_slots: dict[str, list] = defaultdict(list)
        for s in slots:
            section_slots[str(s.section_id or "UNK")].append(s)

        section_dfs: dict[str, pd.DataFrame] = {}
        for sec_pk, slot_list in section_slots.items():
            sec_label = sections.get(sec_pk, sec_pk)
            df = pd.DataFrame("", index=DAYS, columns=PERIODS)
            for s in slot_list:
                if s.day_name in df.index and s.period_label in df.columns:
                    parts = [s.cell_display_line1, s.cell_display_line2, s.cell_display_line3]
                    df.loc[s.day_name, s.period_label] = "\n".join(p for p in parts if p)
            section_dfs[sec_label] = df

        return self.render_from_dataframes(section_dfs, department, academic_year)

    def _render_section_page(
        self, canv: Any, df: pd.DataFrame,
        section_id: str, department: str, academic_year: str,
        page_w: float, page_h: float, now_str: str,
    ) -> None:
        """Draw one section timetable page on the canvas."""
        from reportlab.lib.colors import HexColor, black, white
        from reportlab.lib.units import pt

        days = list(df.index)
        periods = list(df.columns)
        usable_w = page_w - 2 * MARGIN
        usable_h = page_h - 2 * MARGIN - 60  # space for header/footer

        col_widths = [70] + [max(60, (usable_w - 70) / len(periods))] * len(periods)
        row_height = min(CELL_HEIGHT, (usable_h - 28) / (len(days) + 1))

        x_start = MARGIN
        y_start = page_h - MARGIN - 40  # below header

        # ── Page header ──────────────────────────────────────────
        canv.setFillColor(HexColor(f"#{HEADER_COLOUR}"))
        canv.rect(MARGIN, page_h - MARGIN - 30, usable_w, 26, fill=1, stroke=0)
        canv.setFillColor(white)
        canv.setFont("Helvetica-Bold", 13)
        canv.drawString(
            MARGIN + 8, page_h - MARGIN - 18,
            f"{department}  |  Section: {section_id}  |  {academic_year}"
        )

        # ── Header row (periods) ──────────────────────────────────
        y = y_start
        x = x_start
        canv.setFillColor(HexColor(f"#{HEADER_COLOUR}"))
        canv.rect(x, y - 24, col_widths[0], 24, fill=1, stroke=0)
        canv.setFillColor(white)
        canv.setFont("Helvetica-Bold", 8)
        canv.drawCentredString(x + col_widths[0] / 2, y - 16, "Day / Period")

        for i, period in enumerate(periods):
            x += col_widths[i]
            canv.setFillColor(HexColor(f"#{HEADER_COLOUR}"))
            canv.rect(x, y - 24, col_widths[i + 1], 24, fill=1, stroke=0)
            canv.setFillColor(white)
            canv.setFont("Helvetica-Bold", 7)
            short_period = self._shorten_period(str(period))
            canv.drawCentredString(x + col_widths[i + 1] / 2, y - 16, short_period)

        y -= 24

        # ── Day rows ──────────────────────────────────────────────
        for day in days:
            x = x_start
            # Day label
            canv.setFillColor(HexColor(f"#{HEADER_COLOUR}"))
            canv.rect(x, y - row_height, col_widths[0], row_height, fill=1, stroke=0)
            canv.setFillColor(white)
            canv.setFont("Helvetica-Bold", 9)
            canv.drawCentredString(x + col_widths[0] / 2, y - row_height / 2 - 4, str(day)[:3])

            for i, period in enumerate(periods):
                x += col_widths[i]
                cell_text = df.loc[day, period] if day in df.index and period in df.columns else ""
                if pd.isna(cell_text):
                    cell_text = ""
                slot_type = self._detect_type(str(cell_text))
                fill_hex = TYPE_COLOUR.get(slot_type, TYPE_COLOUR["Free"])

                canv.setFillColor(HexColor(f"#{fill_hex}"))
                canv.setStrokeColor(HexColor(f"#{BORDER_COLOUR}"))
                canv.rect(x, y - row_height, col_widths[i + 1], row_height, fill=1, stroke=1)

                # Cell text (truncated)
                canv.setFillColor(black)
                canv.setFont("Helvetica", 7)
                lines = str(cell_text).split("\n")[:3]
                for li, line in enumerate(lines):
                    canv.drawCentredString(
                        x + col_widths[i + 1] / 2,
                        y - row_height + (len(lines) - li) * 14,
                        line[:28],
                    )

            y -= row_height

        # ── Footer ────────────────────────────────────────────────
        canv.setFillColor(HexColor(f"#{BORDER_COLOUR}"))
        canv.setFont("Helvetica", 7)
        canv.drawString(MARGIN, MARGIN, f"Generated by Schedulo  •  {now_str}")
        canv.drawRightString(page_w - MARGIN, MARGIN, "Schedulo — Intelligent University Scheduling")

    def _shorten_period(self, period: str) -> str:
        """Shorten period label for header: '9:00–9:55' → 'P1\n9:00-9:55'"""
        return period.replace("–", "-")

    def _detect_type(self, text: str) -> str:
        if not text.strip():
            return "Free"
        tl = text.lower()
        if "lunch" in tl:
            return "Lunch"
        if "lab cont" in tl:
            return "Lab_Cont"
        if "(lab)" in tl:
            return "Lab"
        if "project" in tl:
            return "Project"
        return "Theory"

    def _get_styles(self) -> Any:
        return {}

    def _stub_pdf(self) -> io.BytesIO:
        buf = io.BytesIO(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n")
        buf.seek(0)
        return buf
