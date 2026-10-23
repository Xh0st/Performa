import io
from pathlib import Path
from xml.sax.saxutils import escape

import font_roboto
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pdf_brand import draw_brand


FONT_DIR = Path(font_roboto.__file__).parent / "files"
pdfmetrics.registerFont(TTFont("AccountRoboto", str(FONT_DIR / "Roboto-Regular.ttf")))
pdfmetrics.registerFont(TTFont("AccountRobotoBold", str(FONT_DIR / "Roboto-Bold.ttf")))
registerFontFamily("AccountRoboto", normal="AccountRoboto", bold="AccountRobotoBold")


def ro_date(value: str) -> str:
    parts = value.split("-")
    return ".".join(reversed(parts)) if len(parts) == 3 else value


def money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def build_account_statement_pdf(
    client: dict,
    statement: dict,
    include_footer: bool = True,
    custom_logo_data_url: str = "",
) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "AccountStatementTitle",
        parent=styles["Title"],
        fontName="AccountRobotoBold",
        fontSize=18,
        leading=22,
        alignment=1,
    )
    normal = ParagraphStyle(
        "AccountStatementBody",
        parent=styles["Normal"],
        fontName="AccountRoboto",
        fontSize=8.5,
        leading=11,
    )
    header = ParagraphStyle(
        "AccountStatementHeader",
        parent=normal,
        fontName="AccountRobotoBold",
        fontSize=7.5,
        textColor=colors.white,
        alignment=1,
    )
    cell = ParagraphStyle("AccountStatementCell", parent=normal, fontSize=7.5, leading=9)
    period = statement["period"]
    period_text = f"{ro_date(period['date_from'])} — {ro_date(period['date_to'])}"
    table_rows = [[
        Paragraph("Data", header),
        Paragraph("Document", header),
        Paragraph("Explicație", header),
        Paragraph("Debit", header),
        Paragraph("Credit", header),
        Paragraph("Sold", header),
    ]]
    for item in statement["all_items"]:
        table_rows.append([
            Paragraph(ro_date(item["date"]), cell),
            Paragraph(escape(item["reference"]), cell),
            Paragraph(escape(item["description"]), cell),
            Paragraph(money(item["debit"]), cell),
            Paragraph(money(item["credit"]), cell),
            Paragraph(money(item["balance"]), cell),
        ])
    if len(table_rows) == 1:
        table_rows.append([Paragraph("—", cell)] + [Paragraph("", cell) for _ in range(5)])
    table = Table(
        table_rows,
        colWidths=[20 * mm, 28 * mm, 64 * mm, 21 * mm, 21 * mm, 22 * mm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#94a3b8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    summary = statement["summary"]
    story = [
        Paragraph("FIȘĂ DE CONT CLIENT", title),
        Spacer(1, 4 * mm),
        Paragraph(f"Client: <b>{escape(client['name'])}</b>", normal),
        Paragraph(f"Perioada: {period_text}", normal),
        Spacer(1, 4 * mm),
        table,
        Spacer(1, 5 * mm),
        Paragraph(
            " · ".join([
                f"Sold inițial: <b>{money(summary['opening'])} RON</b>",
                f"Debit: <b>{money(summary['debit'])} RON</b>",
                f"Credit: <b>{money(summary['credit'])} RON</b>",
                f"Sold final: <b>{money(summary['closing'])} RON</b>",
            ]),
            normal,
        ),
    ]
    document.build(
        story,
        onFirstPage=lambda canvas, page: draw_brand(
            canvas,
            page,
            include_footer,
            custom_logo_data_url,
        ),
        onLaterPages=lambda canvas, page: draw_brand(
            canvas,
            page,
            include_footer,
            custom_logo_data_url,
        ),
    )
    return output.getvalue()