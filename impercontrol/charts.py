from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import QLineF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget


MONTH_NAMES = {
    "01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic",
}


class FinancialChart(QWidget):
    """Gráfica simple de flujo de caja dibujada con Qt.

    En vez de mezclar compras pendientes con gastos, la gráfica compara dos
    magnitudes fáciles de leer: **Entradas** (todo el dinero que realmente
    entró) y **Salidas** (todo el dinero que realmente salió). El flujo neto se muestra como
    una etiqueta sobre cada período, no como una tercera barra negativa.

    Así una compra a crédito aparece en Deudas, pero no provoca una caída en
    caja hasta que se registra un abono.
    """

    def __init__(self, parent=None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self._series: list[dict[str, Any]] = []
        self.compact = compact
        if compact:
            self.setMinimumSize(300, 205)
            self.setMaximumHeight(238)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setMinimumSize(420, 225)
            self.setMaximumHeight(275)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 - API de Qt
        return QSize(390, 225) if self.compact else QSize(760, 255)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - API de Qt
        return QSize(300, 205) if self.compact else QSize(420, 225)

    def set_series(self, rows: Sequence[dict[str, Any]]) -> None:
        self._series = [dict(row) for row in rows]
        self.update()

    @staticmethod
    def _label(period: str) -> str:
        if len(period) == 7 and "-" in period:
            year, month = period.split("-", 1)
            return f"{MONTH_NAMES.get(month, month)}\n{year[-2:]}"
        return period

    @staticmethod
    def _money_short(value: float) -> str:
        absolute = abs(value)
        if absolute >= 1_000_000:
            return f"${absolute / 1_000_000:.1f}M"
        if absolute >= 1_000:
            return f"${absolute / 1_000:.1f}k"
        return f"${absolute:.0f}"

    @staticmethod
    def _net_short(value: float) -> str:
        sign = "+" if value > 0 else "-" if value < 0 else ""
        absolute = abs(value)
        if absolute >= 1_000_000:
            text = f"${absolute / 1_000_000:.1f}M"
        elif absolute >= 1_000:
            text = f"${absolute / 1_000:.1f}k"
        else:
            text = f"${absolute:.0f}"
        return f"{sign}{text}"

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        app = QApplication.instance()
        dark = bool(app and app.property("theme_name") == "Oscuro")
        background = QColor("#182235") if dark else QColor("#ffffff")
        text_color = QColor("#c7d5e8") if dark else QColor("#56657a")
        muted_color = QColor("#96a8bf") if dark else QColor("#738197")
        grid_color = QColor("#2d3b52") if dark else QColor("#e8edf4")
        axis_color = QColor("#5d708b") if dark else QColor("#aab7c8")
        painter.fillRect(self.rect(), background)

        if not self._series:
            painter.setPen(muted_color)
            painter.drawText(self.rect(), Qt.AlignCenter, "No hay movimientos para el período seleccionado")
            return

        if self.compact:
            left, top, right, bottom = 54.0, 43.0, 10.0, 43.0
            grid_steps = 4
            axis_font_size = 7
            net_font_size = 7
        else:
            left, top, right, bottom = 64.0, 47.0, 16.0, 48.0
            grid_steps = 5
            axis_font_size = 8
            net_font_size = 8

        plot = QRectF(
            left,
            top,
            max(self.width() - left - right, 10),
            max(self.height() - top - bottom, 10),
        )

        # Ambas barras parten de cero y siempre se dibujan hacia arriba. Esto
        # evita la impresión de que una deuda pendiente ya salió del efectivo.
        maximum = max(
            [1.0]
            + [float(row.get("income", 0)) for row in self._series]
            + [float(row.get("expenses", 0)) for row in self._series]
        )
        maximum *= 1.16

        def y_for(value: float) -> float:
            return plot.bottom() - (max(value, 0.0) / maximum) * plot.height()

        painter.setFont(QFont("Segoe UI", axis_font_size))
        for step in range(grid_steps + 1):
            value = maximum * step / grid_steps
            y = y_for(value)
            painter.setPen(QPen(grid_color, 1))
            painter.drawLine(QLineF(plot.left(), y, plot.right(), y))
            painter.setPen(muted_color)
            painter.drawText(
                QRectF(0, y - 10, left - 7, 20),
                Qt.AlignRight | Qt.AlignVCenter,
                self._money_short(value),
            )

        painter.setPen(QPen(axis_color, 1.1))
        painter.drawLine(QLineF(plot.left(), plot.bottom(), plot.right(), plot.bottom()))

        colors = {
            "income": QColor("#16a34a"),
            "expenses": QColor("#dc2626"),
            "positive": QColor("#2563eb"),
            "negative": QColor("#b45309"),
        }
        count = len(self._series)
        group_width = plot.width() / max(count, 1)
        bar_gap = 3.0
        maximum_bar_width = 22 if self.compact else 28
        bar_width = max(min((group_width - 10) / 2, maximum_bar_width), 4)

        for index, row in enumerate(self._series):
            center = plot.left() + group_width * (index + 0.5)
            income = max(float(row.get("income", 0)), 0.0)
            outflow = max(float(row.get("expenses", 0)), 0.0)
            net = float(row.get("profit", income - outflow))

            for bar_index, (key, value) in enumerate((("income", income), ("expenses", outflow))):
                x = center + (bar_index - 0.5) * (bar_width + bar_gap) - bar_width / 2
                value_y = y_for(value)
                height = max(plot.bottom() - value_y, 1.0) if value else 0.0
                if height > 0:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(colors[key])
                    painter.drawRoundedRect(QRectF(x, value_y, bar_width, height), 2.5, 2.5)

            painter.setPen(text_color)
            painter.setFont(QFont("Segoe UI", axis_font_size))
            painter.drawText(
                QRectF(center - group_width / 2, plot.bottom() + 5, group_width, 34),
                Qt.AlignHCenter | Qt.AlignTop,
                self._label(str(row.get("period", ""))),
            )

            # Etiqueta del neto: solo se muestra cuando hubo movimiento. Es más
            # fácil de interpretar que una tercera barra por debajo de cero.
            if abs(income) > 0.005 or abs(outflow) > 0.005:
                label_y = max(min(y_for(max(income, outflow)) - 20, plot.bottom() - 22), plot.top())
                painter.setFont(QFont("Segoe UI", net_font_size, QFont.Bold))
                painter.setPen(colors["positive"] if net >= 0 else colors["negative"])
                painter.drawText(
                    QRectF(center - group_width / 2, label_y, group_width, 18),
                    Qt.AlignHCenter | Qt.AlignVCenter,
                    self._net_short(net),
                )

        # Leyenda: dos barras y una explicación explícita del neto.
        painter.setFont(QFont("Segoe UI", axis_font_size))
        legend_x = plot.left()
        for text, key, width in (("Entradas", "income", 88), ("Salidas", "expenses", 82)):
            painter.setBrush(colors[key])
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(legend_x, 14, 11, 11), 3, 3)
            painter.setPen(text_color)
            painter.drawText(QRectF(legend_x + 16, 8, width - 16, 22), Qt.AlignLeft | Qt.AlignVCenter, text)
            legend_x += width
        painter.setPen(muted_color)
        painter.drawText(
            QRectF(legend_x, 8, max(self.width() - legend_x - 8, 70), 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Neto = Entradas − Salidas",
        )
