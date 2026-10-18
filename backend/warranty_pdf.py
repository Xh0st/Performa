import io
from pathlib import Path

import font_roboto
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


FONT_DIR = Path(font_roboto.__file__).parent / "files"
pdfmetrics.registerFont(TTFont("WarrantyRoboto", str(FONT_DIR / "Roboto-Regular.ttf")))
pdfmetrics.registerFont(TTFont("WarrantyRobotoBold", str(FONT_DIR / "Roboto-Bold.ttf")))


def build_certificate(certificate: dict) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "WarrantyTitle",
        parent=styles["Title"],
        fontName="WarrantyRobotoBold",
        fontSize=19,
        leading=24,
        alignment=1,
    )
    normal = ParagraphStyle(
        "WarrantyBody",
        parent=styles["Normal"],
        fontName="WarrantyRoboto",
        fontSize=9,
        leading=13,
    )
    header = ParagraphStyle(
        "WarrantyHeader",
        parent=normal,
        fontName="WarrantyRobotoBold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1,
    )
    cell = ParagraphStyle(
        "WarrantyCell",
        parent=normal,
        fontSize=8,
        leading=10,
    )
    lines = certificate.get("lines", [])
    table_data = [[
        Paragraph("Tip", header),
        Paragraph("Articol / operațiune", header),
        Paragraph("Perioadă", header),
        Paragraph("Valabil până la", header),
    ]]
    for line in lines:
        table_data.append([
            Paragraph(line["label"], cell),
            Paragraph(line["description"], cell),
            Paragraph(f"{line['warranty_months']} luni", cell),
            Paragraph(line["valid_to"], cell),
        ])
    table = Table(table_data, colWidths=[26 * mm, 76 * mm, 28 * mm, 34 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#94a3b8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story = [
        Paragraph("CERTIFICAT DE GARANȚIE", title_style),
        Spacer(1, 5 * mm),
        Paragraph(f"Nr. certificat: <b>{certificate['number']}</b>", normal),
        Paragraph(f"Factura: <b>{certificate['invoice_ref']}</b> · Emis la: {certificate['issued_date']}", normal),
        Paragraph(f"Client: <b>{certificate['client_name']}</b>", normal),
        Paragraph(f"Vehicul: {certificate['vehicle_label']}", normal),
        Spacer(1, 5 * mm),
        table,
        Spacer(1, 5 * mm),
        Paragraph(
            "Garanția acoperă neconformitățile imputabile pieselor sau manoperei executate, "
            "în condițiile utilizării normale și ale documentației tehnice aplicabile. "
            "Pentru reclamații, prezentați factura și certificatul de garanție.",
            normal,
        ),
        Spacer(1, 9 * mm),
        Paragraph(f"Unitate emitentă: {certificate['seller_name']}", normal),
        Paragraph("Reprezentant autorizat: ______________________________", normal),
    ]
    document.build(story)
    return output.getvalue()