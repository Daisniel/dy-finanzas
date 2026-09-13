from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .branding import APP_NAME
from .formatters import format_date


BLUE = colors.HexColor("#2563eb")
GREEN = colors.HexColor("#16a34a")
RED = colors.HexColor("#dc2626")
DARK = colors.HexColor("#172033")
MUTED = colors.HexColor("#66748a")
LIGHT = colors.HexColor("#f1f5f9")
BORDER = colors.HexColor("#dfe6f0")


def _money(value: float) -> str:
    return f"${float(value):,.2f}"


def _period_label(period: str) -> str:
    months = {
        "01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr",
        "05": "May", "06": "Jun", "07": "Jul", "08": "Ago",
        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic",
    }
    if len(period) == 7:
        year, month = period.split("-")
        return f"{months.get(month, month)} {year}"
    return period


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.line(15 * mm, 12 * mm, landscape(A4)[0] - 15 * mm, 12 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(15 * mm, 7 * mm, f"{APP_NAME} - Reporte financiero")
    canvas.drawRightString(landscape(A4)[0] - 15 * mm, 7 * mm, f"Página {doc.page}")
    canvas.restoreState()


def _chart(series: Sequence[Mapping[str, Any]]) -> Drawing:
    width, height = 245 * mm, 78 * mm
    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 18 * mm
    chart.y = 13 * mm
    chart.height = 52 * mm
    chart.width = 214 * mm
    chart.data = [
        [float(row.get("income", 0)) for row in series],
        [float(row.get("expenses", 0)) for row in series],
    ]
    chart.categoryAxis.categoryNames = [_period_label(str(row.get("period", ""))) for row in series]
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.angle = 25 if len(series) > 8 else 0
    chart.categoryAxis.labels.boxAnchor = "ne" if len(series) > 8 else "n"
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(1, max((max(float(row.get("income", 0)), float(row.get("expenses", 0))) for row in series), default=1) * 1.12)
    chart.valueAxis.valueStep = max((chart.valueAxis.valueMax - chart.valueAxis.valueMin) / 5, 1)
    chart.bars[0].fillColor = GREEN
    chart.bars[1].fillColor = RED
    chart.barSpacing = 1
    chart.groupSpacing = 5
    drawing.add(chart)
    drawing.add(String(18 * mm, 70 * mm, "Entradas", fontName="Helvetica-Bold", fontSize=8, fillColor=GREEN))
    drawing.add(String(55 * mm, 70 * mm, "Salidas", fontName="Helvetica-Bold", fontSize=8, fillColor=RED))
    drawing.add(String(92 * mm, 70 * mm, "Neto = Entradas - Salidas", fontName="Helvetica-Bold", fontSize=8, fillColor=BLUE))
    return drawing


def create_financial_report(
    destination: Path | str,
    *,
    start_date: str,
    end_date: str,
    summary: Mapping[str, float],
    series: Sequence[Mapping[str, Any]],
    expense_categories: Sequence[Mapping[str, Any]],
    income_jobs: Sequence[Mapping[str, Any]],
    pending_debts: Sequence[Mapping[str, Any]],
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(destination),
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=17 * mm,
        title=f"Reporte financiero {APP_NAME}",
        author=APP_NAME,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=DARK, spaceAfter=4)
    subtitle = ParagraphStyle("ReportSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=9, textColor=MUTED, spaceAfter=12)
    section = ParagraphStyle("Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=DARK, spaceBefore=8, spaceAfter=7)
    center = ParagraphStyle("Center", parent=styles["Normal"], alignment=TA_CENTER, fontSize=8)

    story = [
        Paragraph("Reporte financiero", title),
        Paragraph(
            f"Período: {format_date(start_date)} al {format_date(end_date)} · Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            subtitle,
        ),
    ]
    cards = [
        ["Dinero en efectivo actual", "Entradas del período", "Salidas del período", "Flujo neto"],
        [_money(summary["cash_balance"]), _money(summary["cash_inflows"]), _money(summary["expenses"]), _money(summary["profit"])],
        ["Deudas pendientes", "Préstamos por cobrar", "Inventario actual", "Compras registradas"],
        [_money(summary["debt_balance"]), _money(summary.get("loans_receivable_balance", 0)), _money(summary["inventory_value"]), _money(summary["material_purchases"])],
    ]
    cards_table = Table(cards, colWidths=[64 * mm] * 4, rowHeights=[8 * mm, 12 * mm, 8 * mm, 12 * mm])
    cards_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("BACKGROUND", (0, 2), (-1, 2), LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTSIZE", (0, 1), (-1, 1), 13),
        ("FONTSIZE", (0, 3), (-1, 3), 13),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [cards_table, Spacer(1, 7 * mm), Paragraph("Flujo de caja", section),
              Paragraph("La gráfica representa caja real: cobros de trabajos, ventas de materiales, aportes externos y devoluciones de préstamos son entradas; gastos, pagos, préstamos entregados y retiros son salidas. Una compra a crédito no reduce el efectivo hasta registrar un abono.", subtitle),
              _chart(series), Spacer(1, 3 * mm)]

    series_data = [["Período", "Entradas", "Salidas", "Flujo neto"]]
    series_data += [[_period_label(str(row["period"])), _money(row["income"]), _money(row["expenses"]), _money(row["profit"])] for row in series]
    series_table = Table(series_data, colWidths=[45 * mm, 43 * mm, 43 * mm, 43 * mm], repeatRows=1)
    series_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]), ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [series_table, PageBreak(), Paragraph("Detalle del período", title)]

    cash_breakdown = [
        ["Concepto financiero", "Monto"],
        ["Cobros de trabajos en efectivo", _money(summary.get("cash_job_income", summary.get("job_income", summary.get("income", 0))))],
        ["Cobros en el extranjero (no efectivo)", _money(summary.get("foreign_job_income", 0))],
        ["Ventas de materiales", _money(summary.get("material_sales", 0))],
        ["Otras entradas", _money(summary.get("manual_inflows", 0))],
        ["Cobros de préstamos", _money(summary.get("loan_repayments", 0))],
        ["Total entradas", _money(summary.get("cash_inflows", 0))],
        ["Total salidas", _money(summary.get("expenses", 0))],
        ["Flujo neto", _money(summary.get("profit", 0))],
    ]
    cash_table = Table(cash_breakdown, colWidths=[80 * mm, 45 * mm], repeatRows=1)
    cash_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
    ]))
    story += [Paragraph("Desglose de entradas y salidas", section), cash_table, Spacer(1, 6 * mm)]

    category_data = [["Categoría de gasto general", "Monto"]] + [[str(row["category"]), _money(row["total"])] for row in expense_categories]
    if len(category_data) == 1:
        category_data.append(["Sin gastos generales registrados", "$0.00"])
    category_table = Table(category_data, colWidths=[80 * mm, 45 * mm], repeatRows=1)
    category_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
    ]))

    jobs_data = [["Cliente", "Trabajo", "Cobrado"]] + [[str(row["client"]), str(row["code"]), _money(row["total"])] for row in income_jobs]
    if len(jobs_data) == 1:
        jobs_data.append(["Sin cobros registrados", "-", "$0.00"])
    jobs_table = Table(jobs_data, colWidths=[55 * mm, 35 * mm, 35 * mm], repeatRows=1)
    jobs_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
    ]))

    detail_grid = Table([
        [Paragraph("Gastos generales por categoría", section), Paragraph("Principales cobros por trabajo", section)],
        [category_table, jobs_table],
    ], colWidths=[132 * mm, 132 * mm])
    detail_grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]))
    story += [detail_grid, Spacer(1, 8 * mm), Paragraph("Deudas pendientes al generar el reporte", section)]

    debt_data = [["Acreedor", "Fecha", "Origen", "Total", "Pagado", "Pendiente"]]
    for row in pending_debts:
        origin = str(row.get("debt_type", "Otra"))
        if row.get("material"):
            origin += f" - {row['material']}"
            if row.get("brand"):
                origin += f" ({row['brand']})"
        debt_data.append([
            str(row["creditor"]), format_date(str(row["debt_date"])), origin,
            _money(row["total_amount"]), _money(row["amount_paid"]), _money(row["balance_due"]),
        ])
    if len(debt_data) == 1:
        debt_data.append(["Sin deudas pendientes", "-", "-", "$0.00", "$0.00", "$0.00"])
    debt_table = Table(debt_data, colWidths=[58 * mm, 28 * mm, 72 * mm, 32 * mm, 32 * mm, 34 * mm], repeatRows=1)
    debt_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [debt_table, Spacer(1, 5 * mm), Paragraph(
        "Nota: El flujo neto de caja incluye todas las entradas y salidas reales, incluidas las ventas de materiales. Los préstamos entregados reducen el efectivo pero no son gastos; sus devoluciones aumentan el efectivo pero no son ingresos operativos. Las compras a crédito pendientes no reducen el efectivo hasta que se pagan.",
        subtitle,
    )]
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return destination
