from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader


LOGO_PATH = Path(__file__).parent.parent / "frontend" / "public" / "performa-logo-dark.png"


def draw_brand(canvas, document, include_footer: bool = True) -> None:
    canvas.saveState()
    page_width, page_height = document.pagesize
    if LOGO_PATH.exists():
        canvas.drawImage(
            ImageReader(str(LOGO_PATH)),
            14 * mm,
            page_height - 15 * mm,
            width=13 * mm,
            height=6 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(colors.HexColor("#f47a2a"))
    canvas.drawString(29 * mm, page_height - 12 * mm, "Performa")
    if include_footer:
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(14 * mm, 7 * mm, "Generat cu Performa - performa.net")
    canvas.restoreState()