import csv
import io
from pathlib import Path

import font_roboto
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
from pdf_brand import draw_brand


HEADERS = [
    "Nr. crt.", "Nr. comandă / deviz", "Data I.F.", "Nr. înmatriculare / VIN",
    "Noxe", "Frâne", "Geometrie", "Faruri / geamuri / parbrize",
    "Parametri / reglaje", "Etanșeitate", "Probă drum", "Persoană prezentatoare",
    "Unitate, inspector și semnătură",
]
FONT_NAME = "DejaVuSans"
FONT_BOLD = "DejaVuSansBold"
FONT_DIR = Path(font_roboto.__file__).parent / "files"
pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_DIR / "Roboto-Regular.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "Roboto-Bold.ttf")))


def table_values(rows: list) -> list:
    return [[row[key] for key in row["columns"]] for row in rows]


def build_pdf(rows: list, start: str, end: str, branch: str, include_footer: bool = True) -> bytes:
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=7 * mm,
        rightMargin=7 * mm,
        topMargin=19 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    styles["Title"].fontName = FONT_BOLD
    styles["Normal"].fontName = FONT_NAME
    title = Paragraph("REGISTRUL DE EVIDENȚĂ A INSPECȚIILOR FINALE — ANEXA 5 RAR", styles["Title"])
    meta = Paragraph(f"Punct de lucru: {branch} · Perioada: {start} — {end}", styles["Normal"])
    header_style = ParagraphStyle(
        "AnexaHeader",
        fontName=FONT_BOLD,
        fontSize=5.3,
        leading=6.1,
        alignment=TA_CENTER,
        textColor=colors.white,
        wordWrap="CJK",
    )
    cell_style = ParagraphStyle(
        "AnexaCell",
        fontName=FONT_NAME,
        fontSize=5.5,
        leading=6.5,
        alignment=TA_CENTER,
        wordWrap="CJK",
    )
    data = [[Paragraph(header, header_style) for header in HEADERS]]
    data.extend([
        [Paragraph(str(value), cell_style) for value in values]
        for values in table_values(rows)
    ])
    widths = [9, 22, 18, 30, 11, 11, 14, 22, 22, 16, 16, 34, 34]
    table = Table(data, colWidths=[value * mm for value in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#94a3b8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    doc.build(
        [title, meta, table],
        onFirstPage=lambda canvas, page: draw_brand(canvas, page, include_footer),
        onLaterPages=lambda canvas, page: draw_brand(canvas, page, include_footer),
    )
    return output.getvalue()


def build_csv(rows: list) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(HEADERS)
    writer.writerows(table_values(rows))
    return output.getvalue().encode("utf-8-sig")


def build_xlsx(rows: list) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Anexa 5 RAR"
    sheet.append(HEADERS)
    for row in table_values(rows):
        sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1E293B")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(max(len(str(cell.value or "")) for cell in column) + 2, 34)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()