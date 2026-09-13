from __future__ import annotations

from datetime import date, datetime
from calendar import monthrange
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .context import ApplicationContext
from .charts import FinancialChart
from .pdf_reports import create_financial_report
from .styles import THEME_NAMES, build_app_style
from .dialogs import (
    CashMovementDialog,
    ClientEditDialog,
    DebtDialog,
    DebtPaymentDialog,
    ExpenseDialog,
    JobDetailDialog,
    LoanDialog,
    LoanRepaymentDialog,
    MaterialMovementDialog,
    MaterialSaleDialog,
    PaymentDialog,
    PaymentRecordDialog,
    PurchasePaymentDialog,
    QuotePreviewDialog,
    WorkerDialog,
)
from .formatters import format_date, round_area
from .icons import icon
from .services import MeasurementTotals
from .ui_components import (
    FlexibleDoubleSpinBox,
    InfoBanner,
    MetricCard,
    Panel,
    button,
    clear_layout,
    configure_table,
    disable_spinbox_wheel,
    refresh_adaptive_metrics,
    status_color,
    ToastNotification,
)


def currency(value: float) -> str:
    return f"${float(value):,.2f}"


def make_date_edit() -> QDateEdit:
    widget = QDateEdit(QDate.currentDate())
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("dd/MM/yyyy")
    return widget


def make_money_spin(value: float = 0.0) -> FlexibleDoubleSpinBox:
    widget = FlexibleDoubleSpinBox()
    widget.setRange(-1_000_000, 1_000_000)
    widget.setDecimals(2)
    widget.setPrefix("$ ")
    widget.setValue(value)
    widget.setButtonSymbols(QAbstractSpinBox.NoButtons)
    return widget


class RefreshablePage(QWidget):
    data_changed = Signal()

    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self.repo = context.repository
        self.services = context.services

    def refresh(self) -> None:
        pass


class DashboardPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)

        # El Dashboard puede ser más alto que la ventana en equipos con escala
        # de pantalla de 125 % o 150 %. Un área desplazable evita que los
        # paneles se compriman o se dibujen unos encima de otros.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        content.setObjectName("PageContent")
        scroll.setWidget(content)
        outer.addWidget(scroll)

        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 6, 6)
        root.setSpacing(16)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(14)
        metrics.setVerticalSpacing(14)
        self.cash_card = MetricCard("Dinero en efectivo", "money", "green", "Disponible real en caja")
        self.income_card = MetricCard("Ingresos del mes", "income", "cyan")
        self.costs_card = MetricCard("Pagos del mes", "expense", "red", "Solo dinero realmente pagado")
        self.profit_card = MetricCard("Flujo neto del mes", "reports", "blue", "Cobros menos pagos realizados")
        self.debt_card = MetricCard("Deudas pendientes", "expense", "amber", "Saldo actual por pagar")
        self.meters_card = MetricCard("Metros realizados", "measure", "purple", "Solo trabajos desde cero")
        self.pending_card = MetricCard("Trabajos pendientes", "jobs", "amber")
        self.maintenance_card = MetricCard("Mantenimientos sugeridos", "calendar", "cyan", "Próximos o vencidos")
        cards = [
            self.cash_card,
            self.income_card,
            self.costs_card,
            self.profit_card,
            self.debt_card,
            self.meters_card,
            self.pending_card,
            self.maintenance_card,
        ]
        for index, widget in enumerate(cards):
            metrics.addWidget(widget, index // 4, index % 4)
        for column in range(4):
            metrics.setColumnStretch(column, 1)
        root.addLayout(metrics)

        # Primera fila: gráfica compacta y trabajos recientes. La gráfica ya no
        # ocupa todo el ancho ni crece verticalmente al redimensionar.
        overview = QGridLayout()
        overview.setHorizontalSpacing(16)
        overview.setVerticalSpacing(16)

        chart_panel = Panel(
            "Flujo de caja",
            "Compara todas las entradas reales de efectivo con todas las salidas reales.",
        )
        chart_panel.setMinimumWidth(360)
        chart_panel.setMaximumWidth(500)
        chart_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        chart_toolbar = QHBoxLayout()
        chart_toolbar.setSpacing(8)
        self.chart_mode = QComboBox()
        self.chart_mode.addItems(["Por meses", "Por años"])
        self.chart_year = QSpinBox()
        self.chart_year.setRange(2000, 2100)
        self.chart_year.setValue(date.today().year)
        self.chart_year.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.chart_year.setMaximumWidth(92)
        chart_toolbar.addWidget(QLabel("Vista"))
        chart_toolbar.addWidget(self.chart_mode)
        chart_toolbar.addWidget(QLabel("Año"))
        chart_toolbar.addWidget(self.chart_year)
        chart_toolbar.addStretch()
        chart_panel.body.addLayout(chart_toolbar)
        chart_panel.body.addWidget(InfoBanner(
            "Incluye cobros de trabajos, aportes externos y cobros de préstamos. Como salidas incluye gastos, pagos de deudas, nómina, préstamos entregados y otros retiros. Una compra a crédito no reduce el efectivo hasta que registras un pago.",
            "info",
        ))
        self.financial_chart = FinancialChart(compact=True)
        chart_panel.body.addWidget(self.financial_chart)
        self.chart_mode.currentTextChanged.connect(self.update_chart)
        self.chart_year.valueChanged.connect(self.update_chart)

        active = Panel(
            "Trabajos en ejecución",
            "Trabajos cuya fecha de inicio ya llegó. Puedes abrirlos o finalizarlos desde aquí.",
        )
        active_toolbar = QHBoxLayout()
        open_active_btn = button("Abrir trabajo", "jobs")
        finish_active_btn = button("Finalizar seleccionado", "save", "primary")
        open_active_btn.clicked.connect(self.open_active_job)
        finish_active_btn.clicked.connect(self.finish_active_job)
        active_toolbar.addStretch()
        active_toolbar.addWidget(open_active_btn)
        active_toolbar.addWidget(finish_active_btn)
        active.body.addLayout(active_toolbar)
        self.jobs_table = QTableWidget()
        configure_table(
            self.jobs_table,
            ["Cliente", "Dirección", "Brigada", "Inicio", "m² cero", "Monto", "Cobrado", "Saldo"],
        )
        self.jobs_table.setMinimumHeight(278)
        self.jobs_table.doubleClicked.connect(self.open_active_job)
        active.body.addWidget(self.jobs_table)

        overview.addWidget(chart_panel, 0, 0)
        overview.addWidget(active, 0, 1)
        overview.setColumnStretch(0, 0)
        overview.setColumnStretch(1, 1)
        root.addLayout(overview)

        # Segunda fila: alertas y deudas. Ambas tablas conservan altura útil
        # aunque la ventana se abra sin maximizar.
        status_grid = QGridLayout()
        status_grid.setSpacing(16)
        alerts = Panel("Alertas de mantenimiento", "Trabajos que se acercan o ya cumplieron 3 años.")
        self.maintenance_table = QTableWidget()
        configure_table(
            self.maintenance_table,
            ["Cliente", "Teléfono", "Realizado", "Mantenimiento", "Estado"],
        )
        self.maintenance_table.setMinimumHeight(220)
        alerts.body.addWidget(self.maintenance_table)

        debts = Panel("Deudas pendientes", "Compras a crédito y otras obligaciones registradas.")
        self.debts_table = QTableWidget()
        configure_table(
            self.debts_table,
            ["Acreedor", "Origen", "Fecha", "Total", "Pagado", "Pendiente"],
        )
        self.debts_table.setMinimumHeight(220)
        debts.body.addWidget(self.debts_table)

        status_grid.addWidget(alerts, 0, 0)
        status_grid.addWidget(debts, 0, 1)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        root.addLayout(status_grid)

        crews = Panel("Rendimiento por brigada", "Solo se contabilizan metros realizados desde cero.")
        self.crews_table = QTableWidget()
        configure_table(
            self.crews_table,
            ["Brigada", "Trabajos finalizados", "Metros desde cero", "Ingresos asociados"],
        )
        self.crews_table.setMinimumHeight(190)
        crews.body.addWidget(self.crews_table)
        root.addWidget(crews)
        self.refresh()

    def selected_active_job_id(self) -> int | None:
        row = self.jobs_table.currentRow()
        if row < 0 or not self.jobs_table.item(row, 0):
            return None
        value = self.jobs_table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def open_active_job(self, *_args) -> None:
        job_id = self.selected_active_job_id()
        if not job_id:
            QMessageBox.information(self, "Selecciona un trabajo", "Selecciona un trabajo en ejecución.")
            return
        JobDetailDialog(self.context, job_id, self, on_saved=self.refresh).exec()
        self.data_changed.emit()

    def finish_active_job(self) -> None:
        job_id = self.selected_active_job_id()
        if not job_id:
            QMessageBox.information(self, "Selecciona un trabajo", "Selecciona el trabajo que terminó.")
            return
        dialog = JobDetailDialog(self.context, job_id, self, on_saved=self.refresh)
        dialog.prepare_finalization()
        dialog.exec()
        self.data_changed.emit()

    def update_chart(self, *_args) -> None:
        if not hasattr(self, "financial_chart"):
            return
        year = self.chart_year.value()
        if self.chart_mode.currentText() == "Por años":
            start = f"{year - 4:04d}-01-01"
            end = f"{year:04d}-12-31"
            grouping = "year"
        else:
            start = f"{year:04d}-01-01"
            end = f"{year:04d}-12-31"
            grouping = "month"
        self.financial_chart.set_series(self.repo.financial_series(start, end, grouping))

    def refresh(self) -> None:
        month = date.today().strftime("%Y-%m")
        warning_days = self.repo.setting_int("maintenance_warning_days", 90)
        snapshot = self.repo.dashboard_snapshot(month, warning_days)
        self.cash_card.set_value(currency(snapshot.cash_balance), "Saldo real después de todas las entradas y salidas")
        self.income_card.set_value(currency(snapshot.income), "Cobros de trabajos y ventas de materiales este mes")
        self.costs_card.set_value(currency(snapshot.costs), "Gastos, deudas, nómina, préstamos y otras salidas")
        self.profit_card.set_value(currency(snapshot.profit), "Todas las entradas menos todas las salidas del mes")
        self.debt_card.set_value(currency(snapshot.debt_balance), f"{snapshot.debt_count} deuda(s) pendiente(s)")
        self.meters_card.set_value(f"{snapshot.completed_meters:,.2f} m²")
        self.pending_card.set_value(str(snapshot.pending_jobs), "Medidos, confirmados o en ejecución")
        self.maintenance_card.set_value(str(snapshot.maintenance_count), "Requieren seguimiento")
        self.update_chart()

        today = date.today().isoformat()
        alerts = self.repo.maintenance_alerts(warning_days)
        self.maintenance_table.setRowCount(len(alerts))
        for r, row in enumerate(alerts):
            state = "Vencido" if row["maintenance_due_date"] <= today else "Próximo"
            values = [
                row["name"],
                row["phone"],
                format_date(row["completion_date"]),
                format_date(row["maintenance_due_date"]),
                state,
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value or "—"))
                if c == 4:
                    item.setForeground(status_color(state))
                self.maintenance_table.setItem(r, c, item)

        debt_rows = self.repo.pending_debts(8)
        self.debts_table.setRowCount(len(debt_rows))
        for r, row in enumerate(debt_rows):
            origin = row["debt_type"]
            if row["material"]:
                origin = f"Materiales · {row['material']}"
                if row["brand"]:
                    origin += f" · {row['brand']}"
            values = [
                row["creditor"],
                origin,
                format_date(row["debt_date"]),
                currency(row["total_amount"]),
                currency(row["amount_paid"]),
                currency(row["balance_due"]),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value or "—"))
                if c == 5:
                    item.setForeground(QColor("#b45309"))
                self.debts_table.setItem(r, c, item)

        jobs = self.repo.active_jobs()
        self.jobs_table.setRowCount(len(jobs))
        for r, row in enumerate(jobs):
            values = [
                row["client"],
                row["address"] or "—",
                row["crew"] or "Sin asignar",
                format_date(row["start_date"]),
                f"{float(row['new_area']):.0f} m²",
                currency(row["agreed_price"]),
                currency(row["paid"]),
                currency(row["balance"]),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, row["id"])
                if c == 7 and float(row["balance"]) > 0.005:
                    item.setForeground(QColor("#b45309"))
                self.jobs_table.setItem(r, c, item)

        crews = self.repo.crew_performance()
        self.crews_table.setRowCount(len(crews))
        for r, row in enumerate(crews):
            values = [
                row["name"],
                row["jobs_count"],
                f"{float(row['meters']):.2f} m²",
                currency(row["amount"]),
            ]
            for c, value in enumerate(values):
                self.crews_table.setItem(r, c, QTableWidgetItem(str(value)))


class ClientsPage(RefreshablePage):
    """History view: clients are created from measurements, not from this page."""

    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(
            InfoBanner(
                "Este apartado sirve para buscar el historial completo de cada cliente. "
                "Cada techo aparece en una fila independiente; los clientes se crean al guardar una medición.",
                "info",
            )
        )
        panel = Panel(
            "Clientes y trabajos",
            "Busca por nombre, teléfono, dirección o código de trabajo. Usa Editar para corregir los datos del cliente.",
        )
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar cliente, teléfono, dirección o trabajo…")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", "#6b778c", 17), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.refresh)
        refresh_btn = button("Actualizar", "refresh")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(refresh_btn)
        panel.body.addLayout(toolbar)

        self.table = QTableWidget()
        configure_table(
            self.table,
            [
                "Cliente", "Teléfono", "Dirección", "Trabajo", "Fecha medición",
                "Desde cero", "Mantenimiento", "Estado", "Finalizado", "Monto", "Editar",
            ],
        )
        self.table.doubleClicked.connect(self.edit_selected_client)
        panel.body.addWidget(self.table)
        root.addWidget(panel, 1)
        self.refresh()

    def selected_client_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def edit_selected_client(self, *_args) -> None:
        client_id = self.selected_client_id()
        if not client_id:
            return
        if ClientEditDialog(self.context, client_id, self).exec():
            self.refresh()
            self.data_changed.emit()

    def edit_client(self, client_id: int) -> None:
        if ClientEditDialog(self.context, client_id, self).exec():
            self.refresh()
            self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        rows = self.repo.client_work_rows(self.search.text() if hasattr(self, "search") else "")
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row["name"], row["phone"] or "—", row["address"] or "—",
                row["work_code"], format_date(row["measured_date"]),
                f"{float(row['new_area']):.0f} m²", f"{float(row['maintenance_area']):.0f} m²",
                row["status"], format_date(row["completion_date"]), currency(row["amount"]),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, row["client_id"])
                if c == 7:
                    item.setForeground(status_color(str(value)))
                self.table.setItem(r, c, item)
            edit_btn = QPushButton()
            edit_btn.setToolTip("Editar nombre, teléfono, dirección y notas")
            edit_btn.setIcon(icon("edit", "#245caa", 17))
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setProperty("role", "ghost")
            edit_btn.clicked.connect(lambda _checked=False, cid=int(row["client_id"]): self.edit_client(cid))
            self.table.setCellWidget(r, 10, edit_btn)


class MeasurementsPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        self.current_id: int | None = None
        self.totals = MeasurementTotals()
        self.calculated_totals = MeasurementTotals()
        self.calculated_price = 0.0
        self.suggested_price = 0.0
        self._final_price_overridden = False
        self._updating_areas = False
        self._loading_materials = False
        self._materials_overridden = False
        self._success_toast: ToastNotification | None = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(2, 2, 8, 8)
        root.setSpacing(16)

        top = QGridLayout()
        top.setSpacing(16)
        input_panel = Panel(
            "1. Medidas recibidas por WhatsApp",
            "Pega el texto completo. Los encabezados Techo y Pretiles se reconocen automáticamente.",
        )
        self.raw_text = QTextEdit()
        self.raw_text.setPlaceholderText(
            "Techo\n4.85 x 10.65\n14.65 x 10.65\n\nPretiles\n1.10 x 14.65 x 2\n…"
        )
        self.raw_text.setMinimumHeight(235)
        parse_btn = button("Interpretar medidas", "refresh", "primary")
        parse_btn.clicked.connect(self.parse_text)
        input_panel.body.addWidget(self.raw_text)
        input_panel.body.addWidget(parse_btn, 0, Qt.AlignRight)
        top.addWidget(input_panel, 0, 0)

        customer_panel = Panel(
            "2. Cliente y estado",
            "Registra aquí nombre, teléfono y dirección sin cambiar de pantalla.",
        )
        self.client = QComboBox()
        self.client.setEditable(True)
        self.client.lineEdit().setPlaceholderText("Selecciona o escribe un cliente")
        self.client.currentIndexChanged.connect(self.load_client_details)
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("Teléfono o teléfonos")
        self.address = QTextEdit()
        self.address.setPlaceholderText("Dirección del techo")
        self.address.setMaximumHeight(72)
        self.measured_date = make_date_edit()
        self.status = QComboBox()
        self.status.addItem("Medido")
        self.status.setEnabled(False)
        self.status.setToolTip("Todo registro nuevo comienza como Medido. Confírmalo después desde Trabajos.")
        self.measure_notes = QTextEdit()
        self.measure_notes.setMaximumHeight(72)
        self.measure_notes.setPlaceholderText("Observaciones de la visita o acuerdo")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("Cliente", self.client)
        form.addRow("Teléfono(s)", self.phone)
        form.addRow("Dirección", self.address)
        form.addRow("Fecha de medición", self.measured_date)
        form.addRow("Estado", self.status)
        form.addRow("Notas", self.measure_notes)
        customer_panel.body.addLayout(form)
        top.addWidget(customer_panel, 0, 1)
        top.setColumnStretch(0, 3)
        top.setColumnStretch(1, 2)
        root.addLayout(top)

        lines_panel = Panel(
            "3. Resultados de las medidas",
            "Puedes corregir cada resultado, la sección, el tipo de trabajo o la observación antes de guardar.",
        )
        self.lines_table = QTableWidget()
        configure_table(
            self.lines_table,
            ["Texto original", "Expresión", "Resultado m²", "Sección", "Tipo", "Observación"],
            editable=True,
        )
        self.lines_table.setMinimumHeight(275)
        self.lines_table.itemChanged.connect(self.recalculate_from_lines)
        lines_panel.body.addWidget(self.lines_table)
        root.addWidget(lines_panel)

        calculations = QGridLayout()
        calculations.setSpacing(16)
        summary = Panel(
            "4. Resumen de superficies",
            "Los valores finales se redondean a metros enteros. Puedes corregirlos manualmente.",
        )
        summary_form = QGridLayout()
        summary_form.setHorizontalSpacing(18)
        summary_form.setVerticalSpacing(8)

        self.new_calculated = QLabel("Calculado: 0,00 m²")
        self.new_calculated.setObjectName("Muted")
        self.new_area_final = FlexibleDoubleSpinBox()
        self.new_area_final.setRange(0, 1_000_000)
        self.new_area_final.setDecimals(0)
        self.new_area_final.setSuffix(" m²")
        self.new_area_final.setButtonSymbols(QAbstractSpinBox.NoButtons)
        disable_spinbox_wheel(self.new_area_final)

        self.maint_calculated = QLabel("Calculado: 0,00 m²")
        self.maint_calculated.setObjectName("Muted")
        self.maint_area_final = FlexibleDoubleSpinBox()
        self.maint_area_final.setRange(0, 1_000_000)
        self.maint_area_final.setDecimals(0)
        self.maint_area_final.setSuffix(" m²")
        self.maint_area_final.setButtonSymbols(QAbstractSpinBox.NoButtons)
        disable_spinbox_wheel(self.maint_area_final)

        self.total_area_value = QLabel("0 m²")
        self.total_area_value.setObjectName("MetricValue")
        total_note = QLabel("Suma final usada para presupuesto, nómina y materiales")
        total_note.setObjectName("Muted")

        for column, title in enumerate(("Desde cero", "Mantenimiento", "Área total")):
            label = QLabel(title)
            label.setObjectName("PanelTitle")
            summary_form.addWidget(label, 0, column)
        summary_form.addWidget(self.new_area_final, 1, 0)
        summary_form.addWidget(self.maint_area_final, 1, 1)
        summary_form.addWidget(self.total_area_value, 1, 2)
        summary_form.addWidget(self.new_calculated, 2, 0)
        summary_form.addWidget(self.maint_calculated, 2, 1)
        summary_form.addWidget(total_note, 2, 2)
        summary.body.addLayout(summary_form)
        self.new_area_final.valueChanged.connect(self.apply_manual_areas)
        self.maint_area_final.valueChanged.connect(self.apply_manual_areas)
        calculations.addWidget(summary, 0, 0, 1, 2)

        budget = Panel(
            "5. Presupuesto",
            "El sistema calcula una sugerencia, pero puedes escribir aquí el precio final acordado.",
        )
        self.price_new = make_money_spin(self.repo.setting_float("price_new", 10.0))
        self.price_new.setSuffix(" / m²")
        self.price_maint = make_money_spin(self.repo.setting_float("price_maintenance", 6.0))
        self.price_maint.setSuffix(" / m²")
        self.masonry = make_money_spin()
        self.membrane = make_money_spin()
        self.adjustment = make_money_spin()

        self.suggested_price_label = QLabel("$0.00")
        self.suggested_price_label.setObjectName("Muted")
        self.final_price = make_money_spin()
        self.final_price.setRange(0, 100_000_000)
        self.final_price.setToolTip(
            "Precio definitivo que se guardará en la medición, el trabajo y el presupuesto de WhatsApp."
        )
        self.final_price.editingFinished.connect(self.mark_final_price_as_manual)
        use_suggested_btn = button("Usar sugerido", "refresh")
        use_suggested_btn.setToolTip("Reemplazar el precio final por el cálculo sugerido")
        use_suggested_btn.clicked.connect(self.use_suggested_price)
        final_price_row = QWidget()
        final_price_layout = QHBoxLayout(final_price_row)
        final_price_layout.setContentsMargins(0, 0, 0, 0)
        final_price_layout.setSpacing(8)
        final_price_layout.addWidget(self.final_price, 1)
        final_price_layout.addWidget(use_suggested_btn)

        for spin in [self.price_new, self.price_maint, self.masonry, self.membrane, self.adjustment]:
            disable_spinbox_wheel(spin)
            spin.valueChanged.connect(self.recalculate_budget)
        disable_spinbox_wheel(self.final_price)
        budget_form = QFormLayout()
        budget_form.setVerticalSpacing(9)
        budget_form.addRow("Desde cero", self.price_new)
        budget_form.addRow("Mantenimiento", self.price_maint)
        budget_form.addRow("Albañilería", self.masonry)
        budget_form.addRow("Retiro de manta", self.membrane)
        budget_form.addRow("Ajuste / descuento", self.adjustment)
        budget_form.addRow("Precio sugerido", self.suggested_price_label)
        budget_form.addRow("Precio final acordado", final_price_row)
        budget.body.addLayout(budget_form)
        calculations.addWidget(budget, 1, 0)

        materials = Panel(
            "6. Materiales previstos",
            "El sistema sugiere cantidades según el área y el stock. Puedes corregirlas antes de guardar.",
        )
        material_actions = QHBoxLayout()
        add_material = button("Agregar material", "plus")
        remove_material = button("Quitar seleccionado", "delete", "danger")
        reset_materials = button("Restablecer sugerencia", "refresh")
        add_material.clicked.connect(self.add_measurement_material)
        remove_material.clicked.connect(self.remove_measurement_material)
        reset_materials.clicked.connect(self.reset_measurement_materials)
        material_actions.addWidget(add_material)
        material_actions.addWidget(remove_material)
        material_actions.addStretch()
        material_actions.addWidget(reset_materials)
        materials.body.addLayout(material_actions)

        self.measurement_materials_table = QTableWidget()
        configure_table(
            self.measurement_materials_table,
            ["Material", "Cantidad", "Litros", "Stock", "Costo estimado", "Notas"],
            editable=True,
        )
        self.measurement_materials_table.setMinimumHeight(205)
        self.measurement_materials_table.itemChanged.connect(
            self._measurement_material_item_changed
        )
        materials.body.addWidget(self.measurement_materials_table)
        calculations.addWidget(materials, 1, 1)
        root.addLayout(calculations)

        actions_panel = Panel()
        actions = QHBoxLayout()
        new_btn = button("Nueva medición", "plus")
        history_btn = button("Mediciones guardadas", "calendar")
        quote_btn = button("Vista previa para WhatsApp", "copy")
        save_btn = button("Guardar registro", "save", "primary")
        new_btn.clicked.connect(self.clear_form)
        history_btn.clicked.connect(self.show_history)
        quote_btn.clicked.connect(self.show_quote_preview)
        # ``clicked`` emits a bool (checked). No se debe pasar ese valor como
        # ``show_message`` porque un botón normal emite False y saltaría la
        # limpieza y la notificación de éxito.
        save_btn.clicked.connect(lambda _checked=False: self.save_measurement())
        actions.addWidget(new_btn)
        actions.addWidget(history_btn)
        actions.addStretch()
        actions.addWidget(quote_btn)
        actions.addWidget(save_btn)
        actions_panel.body.addLayout(actions)
        root.addWidget(actions_panel)

        scroll.setWidget(container)
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(scroll)
        self.refresh()
        self.recalculate_from_lines()

    def refresh(self) -> None:
        if not hasattr(self, "client"):
            return
        current = self.client.currentData()
        typed = self.client.currentText()
        self.client.blockSignals(True)
        self.client.clear()
        self.client.addItem("Selecciona o escribe un cliente", None)
        for row in self.repo.clients_for_combo():
            suffix = f" — {row['phone']}" if row["phone"] else ""
            self.client.addItem(f"{row['name']}{suffix}", row["id"])
        idx = self.client.findData(current)
        if idx >= 0:
            self.client.setCurrentIndex(idx)
        elif typed and typed != "Selecciona o escribe un cliente":
            self.client.setEditText(typed)
        else:
            self.client.setCurrentIndex(0)
        self.client.blockSignals(False)

    def load_client_details(self, *_args) -> None:
        client_id = self.client.currentData()
        if not client_id:
            return
        row = self.repo.get_client(int(client_id))
        if row:
            self.phone.setText(row["phone"] or "")
            self.address.setPlainText(row["address"] or "")

    def parse_text(self) -> None:
        parsed = self.services.measurements.parse(self.raw_text.toPlainText())
        self.lines_table.blockSignals(True)
        self.lines_table.setRowCount(len(parsed))
        for r, line in enumerate(parsed):
            values = [
                line.original_text, line.expression, f"{line.result:.2f}", line.section,
                line.work_type, line.observation or line.error,
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c in (0, 1):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if not line.valid:
                    item.setBackground(QColor("#fef2f2"))
                    item.setForeground(QColor("#b91c1c"))
                self.lines_table.setItem(r, c, item)
        self.lines_table.blockSignals(False)
        self.recalculate_from_lines()

    def _rows_from_table(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in range(self.lines_table.rowCount()):
            try:
                result = float(self.lines_table.item(row, 2).text().replace(",", "."))
            except (ValueError, AttributeError):
                result = 0.0
            rows.append(
                {
                    "original_text": self.lines_table.item(row, 0).text() if self.lines_table.item(row, 0) else "",
                    "expression": self.lines_table.item(row, 1).text() if self.lines_table.item(row, 1) else "",
                    "result": result,
                    "section": self.lines_table.item(row, 3).text() if self.lines_table.item(row, 3) else "Techo",
                    "work_type": self.lines_table.item(row, 4).text() if self.lines_table.item(row, 4) else "Desde cero",
                    "observation": self.lines_table.item(row, 5).text() if self.lines_table.item(row, 5) else "",
                }
            )
        return rows

    def recalculate_from_lines(
        self,
        *_args,
        update_final: bool = True,
        refresh_materials: bool | None = None,
    ) -> None:
        if refresh_materials is None:
            changed_item = _args[0] if _args else None
            refresh_materials = not isinstance(changed_item, QTableWidgetItem) or changed_item.column() in (1, 2, 4)
        self.calculated_totals = self.services.measurements.totals_from_rows(self._rows_from_table())
        self.new_calculated.setText(f"Calculado: {self.calculated_totals.new_area:.2f} m²".replace(".", ","))
        self.maint_calculated.setText(f"Calculado: {self.calculated_totals.maintenance_area:.2f} m²".replace(".", ","))
        if update_final:
            self._updating_areas = True
            self.new_area_final.setValue(round_area(self.calculated_totals.new_area))
            self.maint_area_final.setValue(round_area(self.calculated_totals.maintenance_area))
            self._updating_areas = False
        self.apply_manual_areas(refresh_materials=refresh_materials)

    def apply_manual_areas(self, *_args, refresh_materials: bool = False) -> None:
        if self._updating_areas:
            return
        new_area = float(self.new_area_final.value())
        maintenance = float(self.maint_area_final.value())
        self.totals = MeasurementTotals(new_area, maintenance, new_area + maintenance)
        self.total_area_value.setText(f"{int(self.totals.total_area)} m²")
        self.recalculate_budget()
        if refresh_materials or not self._materials_overridden:
            self.load_suggested_measurement_materials(force=refresh_materials)

    def _measurement_material_choices(self) -> list[Any]:
        return list(self.repo.list_materials(True))

    def _append_measurement_material_row(
        self,
        material_id: int | None = None,
        quantity: float = 0.0,
        notes: str = "",
    ) -> None:
        was_loading = self._loading_materials
        self._loading_materials = True
        try:
            row = self.measurement_materials_table.rowCount()
            self.measurement_materials_table.insertRow(row)
            combo = QComboBox()
            for material in self._measurement_material_choices():
                combo.addItem(
                    material["name"],
                    (
                        int(material["id"]),
                        float(material["package_size"]),
                        float(material["average_unit_cost"]),
                        float(material["stock_quantity"]),
                        str(material["unit"]),
                        str(material["category"]),
                    ),
                )
            if material_id is not None:
                for index in range(combo.count()):
                    data = combo.itemData(index)
                    if data and int(data[0]) == int(material_id):
                        combo.setCurrentIndex(index)
                        break
            self.measurement_materials_table.setCellWidget(row, 0, combo)
            combo.currentIndexChanged.connect(
                lambda _index, widget=combo: self._measurement_material_combo_changed(widget)
            )
            self.measurement_materials_table.setItem(
                row, 1, QTableWidgetItem(f"{float(quantity):.2f}")
            )
            liters_item = QTableWidgetItem("0.00")
            liters_item.setFlags(liters_item.flags() & ~Qt.ItemIsEditable)
            self.measurement_materials_table.setItem(row, 2, liters_item)
            stock_item = QTableWidgetItem("")
            stock_item.setFlags(stock_item.flags() & ~Qt.ItemIsEditable)
            self.measurement_materials_table.setItem(row, 3, stock_item)
            cost_item = QTableWidgetItem("$0.00")
            cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
            self.measurement_materials_table.setItem(row, 4, cost_item)
            self.measurement_materials_table.setItem(row, 5, QTableWidgetItem(notes))
        finally:
            self._loading_materials = was_loading
        self._update_measurement_material_row(row)

    def _measurement_material_row_for_combo(self, combo: QComboBox) -> int:
        for row in range(self.measurement_materials_table.rowCount()):
            if self.measurement_materials_table.cellWidget(row, 0) is combo:
                return row
        return -1

    def _measurement_material_combo_changed(self, combo: QComboBox) -> None:
        row = self._measurement_material_row_for_combo(combo)
        if row >= 0:
            self._materials_overridden = True
            self._update_measurement_material_row(row)

    @staticmethod
    def _table_number(item: QTableWidgetItem | None) -> float:
        try:
            return float((item.text() if item else "0").replace(",", "."))
        except ValueError:
            return 0.0

    def _update_measurement_material_row(self, row: int) -> None:
        if self._loading_materials or row < 0:
            return
        combo = self.measurement_materials_table.cellWidget(row, 0)
        if not isinstance(combo, QComboBox) or not combo.currentData():
            return
        _material_id, package_size, average_cost, stock, unit, category = combo.currentData()
        quantity = self._table_number(self.measurement_materials_table.item(row, 1))
        liters = quantity * float(package_size) if str(category) == "Pintura" else 0.0
        self._loading_materials = True
        self.measurement_materials_table.item(row, 2).setText(f"{liters:.2f}")
        self.measurement_materials_table.item(row, 3).setText(
            f"{float(stock):.2f} {unit}(s)"
        )
        self.measurement_materials_table.item(row, 4).setText(
            f"${quantity * float(average_cost):,.2f}"
        )
        self._loading_materials = False

    def _measurement_material_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading_materials:
            return
        if item.column() in (1, 5):
            self._materials_overridden = True
        if item.column() == 1:
            self._update_measurement_material_row(item.row())

    def load_suggested_measurement_materials(self, *, force: bool = False) -> None:
        if self._materials_overridden and not force:
            return
        rows = self.repo.suggest_material_plan(
            self.totals.new_area,
            self.totals.maintenance_area,
            self.repo.setting_float("paint_coverage_m2", 25.0),
            self.repo.setting_float("mesh_roll_coverage_m2", 100.0),
        )
        self._loading_materials = True
        self.measurement_materials_table.setRowCount(0)
        self._loading_materials = False
        for row in rows:
            self._append_measurement_material_row(
                int(row["material_id"]),
                float(row["quantity"]),
                str(row["notes"]),
            )
        self._materials_overridden = False

    def load_saved_measurement_materials(self, job_id: int) -> None:
        rows = self.repo.job_material_plan(job_id)
        if not rows:
            self._materials_overridden = False
            self.load_suggested_measurement_materials(force=True)
            return
        self._loading_materials = True
        self.measurement_materials_table.setRowCount(0)
        self._loading_materials = False
        for row in rows:
            self._append_measurement_material_row(
                int(row["material_id"]),
                float(row["quantity"]),
                row["notes"] or "",
            )
        self._materials_overridden = True

    def add_measurement_material(self) -> None:
        used = {
            int(self.measurement_materials_table.cellWidget(row, 0).currentData()[0])
            for row in range(self.measurement_materials_table.rowCount())
            if isinstance(self.measurement_materials_table.cellWidget(row, 0), QComboBox)
            and self.measurement_materials_table.cellWidget(row, 0).currentData()
        }
        available = [
            row for row in self._measurement_material_choices() if int(row["id"]) not in used
        ]
        if not available:
            QMessageBox.information(
                self, "Sin más materiales", "Todos los tipos de material ya están incluidos."
            )
            return
        self._materials_overridden = True
        self._append_measurement_material_row(
            int(available[0]["id"]), 0.0, "Agregado manualmente"
        )

    def remove_measurement_material(self) -> None:
        row = self.measurement_materials_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Selecciona un material", "Selecciona la fila que deseas quitar."
            )
            return
        self._materials_overridden = True
        self.measurement_materials_table.removeRow(row)

    def reset_measurement_materials(self) -> None:
        self._materials_overridden = False
        self.load_suggested_measurement_materials(force=True)

    def measurement_material_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        used: set[int] = set()
        for row in range(self.measurement_materials_table.rowCount()):
            combo = self.measurement_materials_table.cellWidget(row, 0)
            if not isinstance(combo, QComboBox) or not combo.currentData():
                continue
            material_id, package_size, _average_cost, _stock, _unit, category = combo.currentData()
            material_id = int(material_id)
            if material_id in used:
                raise ValueError("Un mismo tipo de material no puede aparecer dos veces.")
            used.add(material_id)
            quantity = self._table_number(self.measurement_materials_table.item(row, 1))
            if quantity < 0:
                raise ValueError(f"La cantidad de la fila {row + 1} no puede ser negativa.")
            liters = quantity * float(package_size) if str(category) == "Pintura" else 0.0
            rows.append(
                {
                    "material_id": material_id,
                    "quantity": quantity,
                    "liters": liters,
                    "notes": self.measurement_materials_table.item(row, 5).text().strip()
                    if self.measurement_materials_table.item(row, 5)
                    else "",
                }
            )
        return rows

    def recalculate_budget(self, *_args) -> None:
        self.suggested_price = self.services.measurements.calculate_price(
            self.totals,
            self.price_new.value(),
            self.price_maint.value(),
            self.masonry.value(),
            self.membrane.value(),
            self.adjustment.value(),
        )
        self.suggested_price_label.setText(currency(self.suggested_price))
        if not self._final_price_overridden:
            self.final_price.blockSignals(True)
            self.final_price.setValue(self.suggested_price)
            self.final_price.blockSignals(False)
        self.calculated_price = float(self.final_price.value())

    def mark_final_price_as_manual(self) -> None:
        self._final_price_overridden = True
        self.calculated_price = float(self.final_price.value())

    def use_suggested_price(self) -> None:
        self._final_price_overridden = False
        self.final_price.blockSignals(True)
        self.final_price.setValue(self.suggested_price)
        self.final_price.blockSignals(False)
        self.calculated_price = self.suggested_price

    def clear_form(self) -> None:
        self.current_id = None
        self.client.setCurrentIndex(0)
        self.phone.clear()
        self.address.clear()
        self.raw_text.clear()
        self.lines_table.setRowCount(0)
        self.measured_date.setDate(QDate.currentDate())
        self.status.setCurrentText("Medido")
        self.measure_notes.clear()
        self.price_new.setValue(self.repo.setting_float("price_new", 10.0))
        self.price_maint.setValue(self.repo.setting_float("price_maintenance", 6.0))
        self.masonry.setValue(0)
        self.membrane.setValue(0)
        self.adjustment.setValue(0)
        self._final_price_overridden = False
        self.final_price.blockSignals(True)
        self.final_price.setValue(0)
        self.final_price.blockSignals(False)
        self.calculated_totals = MeasurementTotals()
        self._updating_areas = True
        self.new_area_final.setValue(0)
        self.maint_area_final.setValue(0)
        self._updating_areas = False
        self._materials_overridden = False
        self._loading_materials = True
        self.measurement_materials_table.setRowCount(0)
        self._loading_materials = False
        self.apply_manual_areas()
        self.raw_text.setFocus()

    def _show_success_toast(self, message: str) -> None:
        if self._success_toast is not None:
            self._success_toast.dismiss()
        toast = ToastNotification(message, self)
        self._success_toast = toast
        toast.closed.connect(lambda toast=toast: self._clear_success_toast(toast))
        toast.show_toast()

    def _clear_success_toast(self, toast: ToastNotification) -> None:
        if self._success_toast is toast:
            self._success_toast = None

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self._success_toast is not None:
            self._success_toast.reposition()

    def _ensure_client(self) -> int | None:
        typed = self.client.currentText().split(" — ", 1)[0].strip()
        if not typed or typed == "Selecciona o escribe un cliente":
            QMessageBox.warning(self, "Cliente requerido", "Escribe o selecciona el nombre del cliente.")
            return None
        client_id = self.client.currentData()
        if client_id:
            existing = self.repo.get_client(int(client_id))
            self.repo.save_client(
                typed,
                self.phone.text().strip(),
                self.address.toPlainText().strip(),
                existing["notes"] if existing else "",
                int(client_id),
            )
            return int(client_id)
        client_id = self.repo.save_client(
            typed,
            self.phone.text().strip(),
            self.address.toPlainText().strip(),
            "",
        )
        self.refresh()
        self.client.setCurrentIndex(self.client.findData(client_id))
        return client_id

    def save_measurement(self, show_message: bool = True) -> int | None:
        client_id = self._ensure_client()
        if not client_id:
            return None
        if self.lines_table.rowCount() == 0:
            self.parse_text()
        if self.totals.total_area <= 0:
            QMessageBox.warning(self, "Medición vacía", "No hay metros calculados para guardar.")
            return None
        existing_job = (
            self.repo.job_for_measurement(self.current_id)
            if self.current_id is not None
            else None
        )
        record_status = existing_job["status"] if existing_job else "Medido"
        try:
            material_rows = self.measurement_material_rows()
        except ValueError as exc:
            QMessageBox.warning(self, "Materiales inválidos", str(exc))
            return None
        previous_material_plan: list[dict[str, object]] = []
        if existing_job and existing_job["status"] in {"En Progreso", "Finalizado"}:
            previous_material_plan = [
                {
                    "material_id": int(row["material_id"]),
                    "quantity": float(row["quantity"]),
                    "notes": row["notes"] or "",
                }
                for row in self.repo.job_material_plan(int(existing_job["id"]))
            ]
        material_messages: list[str] = []
        try:
            measurement_id = self.services.measurements.save(
                client_id=client_id,
                measured_date=self.measured_date.date().toString("yyyy-MM-dd"),
                raw_text=self.raw_text.toPlainText(),
                rows=self._rows_from_table(),
                totals=self.totals,
                price_new=self.price_new.value(),
                price_maintenance=self.price_maint.value(),
                masonry_extra=self.masonry.value(),
                membrane_extra=self.membrane.value(),
                manual_adjustment=self.adjustment.value(),
                final_price=float(self.final_price.value()),
                status=record_status,
                notes=self.measure_notes.toPlainText().strip(),
                measurement_id=self.current_id,
            )
            job_id = self.repo.upsert_job_from_measurement(
                measurement_id=measurement_id,
                client_id=client_id,
                status=record_status,
                new_area=self.totals.new_area,
                maintenance_area=self.totals.maintenance_area,
                agreed_price=float(self.final_price.value()),
                notes=self.measure_notes.toPlainText().strip(),
            )
            self.repo.save_job_material_plan(job_id, material_rows)
            if existing_job and existing_job["status"] in {"En Progreso", "Finalizado"}:
                current_job = self.repo.get_job(job_id)
                movement_date = (
                    current_job["completion_date"]
                    or current_job["start_date"]
                    or self.measured_date.date().toString("yyyy-MM-dd")
                ) if current_job else self.measured_date.date().toString("yyyy-MM-dd")
                try:
                    material_messages = self.repo.reconcile_job_materials_to_plan(
                        job_id,
                        movement_date=str(movement_date),
                        note_prefix="Ajuste por edición de medidas",
                    )
                except ValueError:
                    # Keep the previous plan if the new dimensions require
                    # more stock than is currently available.
                    self.repo.save_job_material_plan(job_id, previous_material_plan)
                    raise
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return None
        self.current_id = measurement_id
        if show_message:
            job = self.repo.get_job(job_id)
            job_code = job["code"] if job else job_id
            self.clear_form()
            self._show_success_toast(
                f"Registro guardado ({job_code}). "
                "El formulario está listo para una nueva medición."
                + (" Materiales e inventario actualizados." if material_messages else "")
            )
        self.data_changed.emit()
        return measurement_id

    def show_quote_preview(self) -> None:
        if self.lines_table.rowCount() == 0:
            self.parse_text()
        if self.totals.total_area <= 0:
            QMessageBox.warning(self, "Sin medidas", "Primero interpreta las medidas.")
            return
        text = self.services.measurements.build_whatsapp_quote(
            self._rows_from_table(), self.totals.total_area, float(self.final_price.value())
        )
        QuotePreviewDialog(text, self).exec()

    def show_history(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Mediciones guardadas")
        dialog.resize(1050, 620)
        panel = Panel("Historial de mediciones", "Selecciona una medición para cargarla y continuar trabajando.")
        table = QTableWidget()
        configure_table(
            table,
            ["Fecha", "Cliente", "Desde cero", "Mantenimiento", "Total", "Presupuesto", "Estado"],
        )
        rows = self.repo.all_measurements(500)
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                format_date(row["measured_date"]), row["client"], f"{float(row['new_area']):.0f}",
                f"{float(row['maintenance_area']):.0f}", f"{float(row['total_area']):.0f}",
                currency(row["final_price"]), row["status"],
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, row["id"])
                if c == 6:
                    item.setForeground(status_color(row["status"]))
                table.setItem(r, c, item)
        panel.body.addWidget(table)
        open_btn = button("Cargar medición", "measure", "primary")
        close_btn = button("Cerrar")

        def load() -> None:
            row_index = table.currentRow()
            if row_index < 0:
                QMessageBox.information(dialog, "Selecciona una fila", "Selecciona una medición para cargarla.")
                return
            measurement_id = table.item(row_index, 0).data(Qt.UserRole)
            dialog.accept()
            self.load_measurement(int(measurement_id))

        open_btn.clicked.connect(load)
        close_btn.clicked.connect(dialog.reject)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(close_btn)
        actions.addWidget(open_btn)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addLayout(actions)
        dialog.exec()

    def load_measurement(self, measurement_id: int) -> None:
        row = self.repo.get_measurement(measurement_id)
        if not row:
            return
        self.current_id = measurement_id
        self.client.setCurrentIndex(self.client.findData(row["client_id"]))
        self.load_client_details()
        measured = QDate.fromString(row["measured_date"], "yyyy-MM-dd")
        if measured.isValid():
            self.measured_date.setDate(measured)
        self.raw_text.setPlainText(row["raw_text"])
        self.status.setCurrentText(row["status"])
        self.measure_notes.setPlainText(row["notes"])
        self.price_new.setValue(float(row["price_new"]))
        self.price_maint.setValue(float(row["price_maintenance"]))
        self.masonry.setValue(float(row["masonry_extra"]))
        self.membrane.setValue(float(row["membrane_extra"]))
        self.adjustment.setValue(float(row["manual_adjustment"]))
        lines = self.repo.measurement_lines(measurement_id)
        self.lines_table.blockSignals(True)
        self.lines_table.setRowCount(len(lines))
        for r, line in enumerate(lines):
            values = [
                line["original_text"], line["expression"], f"{float(line['result']):.2f}",
                line["section"], line["work_type"], line["observation"],
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c in (0, 1):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.lines_table.setItem(r, c, item)
        self.lines_table.blockSignals(False)
        self.recalculate_from_lines(update_final=False, refresh_materials=False)
        self._updating_areas = True
        self.new_area_final.setValue(float(row["new_area"]))
        self.maint_area_final.setValue(float(row["maintenance_area"]))
        self._updating_areas = False
        self.apply_manual_areas()
        saved_final_price = float(row["final_price"])
        self.final_price.blockSignals(True)
        self.final_price.setValue(saved_final_price)
        self.final_price.blockSignals(False)
        self.calculated_price = saved_final_price
        self._final_price_overridden = abs(saved_final_price - self.suggested_price) > 0.005
        job = self.repo.job_for_measurement(measurement_id)
        if job:
            self.load_saved_measurement_materials(int(job["id"]))
        else:
            self._materials_overridden = False
            self.load_suggested_measurement_materials(force=True)

class JobsPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(
            InfoBanner(
                "Busca por cliente, dirección o teléfono. Al confirmar un trabajo podrás indicar la fecha de inicio; al llegar esa fecha pasará automáticamente a En Progreso.",
                "info",
            )
        )
        panel = Panel("Trabajos", "Filtra por estado y localiza registros aunque solo recuerdes parte de los datos.")
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por cliente, dirección o teléfono…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.filter = QComboBox()
        self.filter.addItems(["Todos", "Medido", "Confirmado", "En Progreso", "Finalizado", "Mantenimiento sugerido"])
        self.filter.currentTextChanged.connect(self.refresh)
        open_btn = button("Abrir trabajo", "jobs", "primary")
        delete_btn = button("Eliminar trabajo", "delete", "danger")
        contact_btn = button("Registrar contacto de mantenimiento", "calendar")
        refresh_btn = button("Actualizar", "refresh")
        open_btn.clicked.connect(self.open_job)
        delete_btn.clicked.connect(self.delete_job)
        contact_btn.clicked.connect(self.register_maintenance_contact)
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(QLabel("Estado"))
        toolbar.addWidget(self.filter)
        toolbar.addStretch()
        toolbar.addWidget(contact_btn)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(delete_btn)
        toolbar.addWidget(open_btn)
        panel.body.addLayout(toolbar)
        self.table = QTableWidget()
        configure_table(
            self.table,
            [
                "Cliente", "Teléfono", "Dirección", "Fecha medición", "Fecha inicio",
                "Brigada", "Desde cero", "Mant.", "Monto", "Estado", "Finalizado", "Mantenimiento",
            ],
        )
        self.table.doubleClicked.connect(self.open_job)
        panel.body.addWidget(self.table)
        layout.addWidget(panel, 1)
        self.refresh()

    def selected_job_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def open_job(self, *_args) -> None:
        job_id = self.selected_job_id()
        if not job_id:
            QMessageBox.information(self, "Selecciona un trabajo", "Selecciona una fila para abrirla.")
            return
        JobDetailDialog(self.context, job_id, self, on_saved=self.refresh).exec()
        self.data_changed.emit()

    def delete_job(self) -> None:
        job_id = self.selected_job_id()
        if not job_id:
            QMessageBox.information(self, "Selecciona un trabajo", "Selecciona el trabajo que deseas eliminar.")
            return
        job = self.repo.get_job(job_id)
        if not job:
            self.refresh()
            return
        answer = QMessageBox.question(
            self,
            "Eliminar trabajo",
            f"¿Eliminar el trabajo {job['code']} de {job['client_name']}?\n\n"
            "Se eliminarán sus pagos, nómina y plan de materiales. "
            "La medición se conservará para poder recuperarla después. "
            "Si había materiales consumidos, se devolverán al inventario.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repo.delete_job(job_id)
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo eliminar", str(exc))
            return
        self.refresh()
        self.data_changed.emit()

    def register_maintenance_contact(self) -> None:
        job_id = self.selected_job_id()
        if not job_id:
            QMessageBox.information(self, "Selecciona un trabajo", "Selecciona el trabajo contactado.")
            return
        result, ok = QInputDialog.getMultiLineText(
            self,
            "Seguimiento de mantenimiento",
            "Resultado del contacto con el cliente",
        )
        if not ok:
            return
        self.repo.register_maintenance_contact(job_id, result.strip())
        self.refresh()
        self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        warning_days = self.repo.setting_int("maintenance_warning_days", 90)
        rows = self.repo.list_jobs(
            self.filter.currentText(), warning_days, self.search.text()
        )
        today = date.today().isoformat()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row["client"], row["phone"] or "—", row["address"] or "—",
                format_date(row["measurement_date"]), format_date(row["start_date"]),
                row["crew"] or "Sin asignar",
                f"{float(row['new_area']):.0f} m²", f"{float(row['maintenance_area']):.0f} m²",
                currency(row["agreed_price"]), row["status"], format_date(row["completion_date"]),
                format_date(row["maintenance_due_date"]),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, row["id"])
                if c == 9:
                    item.setForeground(status_color(row["status"]))
                if c == 11 and row["maintenance_due_date"] and row["maintenance_due_date"] <= today and not row["maintenance_contacted"]:
                    item.setForeground(QColor("#b91c1c"))
                self.table.setItem(r, c, item)


class BrigadesPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(
            InfoBanner(
                "La composición mostrada es habitual. En cada trabajo puedes sustituir personas o cambiar su función sin alterar esta configuración.",
                "info",
            )
        )
        panel = Panel("Brigadas y trabajadores", "Metros acumulados únicamente por participación en trabajos desde cero.")
        toolbar = QHBoxLayout()
        add = button("Agregar trabajador", "plus", "primary")
        edit = button("Editar seleccionado", "measure")
        add.clicked.connect(self.add_worker)
        edit.clicked.connect(self.edit_worker)
        toolbar.addStretch()
        toolbar.addWidget(edit)
        toolbar.addWidget(add)
        panel.body.addLayout(toolbar)
        self.table = QTableWidget()
        configure_table(
            self.table,
            ["Trabajador", "Brigada habitual", "Rol habitual", "Socio", "Estado", "Metros desde cero", "Pago acumulado"],
        )
        self.table.doubleClicked.connect(self.edit_worker)
        panel.body.addWidget(self.table)
        layout.addWidget(panel, 1)
        self.refresh()

    def selected_worker_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def add_worker(self) -> None:
        if WorkerDialog(self.context, parent=self).exec():
            self.refresh()
            self.data_changed.emit()

    def edit_worker(self, *_args) -> None:
        worker_id = self.selected_worker_id()
        if worker_id and WorkerDialog(self.context, worker_id, self).exec():
            self.refresh()
            self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        rows = self.repo.list_workers(False)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row["name"], row["crew"] or "Sin brigada", row["base_role"],
                "Sí" if row["is_partner"] else "No", "Activo" if row["active"] else "Inactivo",
                f"{float(row['meters']):.2f} m²", currency(row["pay"]),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, row["id"])
                if c == 4:
                    item.setForeground(status_color(str(value)))
                self.table.setItem(r, c, item)


class MaterialsPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        financial = QGridLayout()
        financial.setSpacing(14)
        self.investment_card = MetricCard(
            "Invertido en inventario actual", "money", "blue",
            "Valor de compra aproximado de los materiales que todavía están disponibles.",
        )
        self.payable_card = MetricCard(
            "Pendiente con proveedores", "expense", "red",
            "Saldo de compras a crédito o con pagos parciales.",
        )
        self.paid_card = MetricCard(
            "Pagado en compras registradas", "check", "green",
            "Suma pagada a proveedores dentro del historial de materiales.",
        )
        financial.addWidget(self.investment_card, 0, 0)
        financial.addWidget(self.payable_card, 0, 1)
        financial.addWidget(self.paid_card, 0, 2)
        layout.addLayout(financial)

        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(14)
        layout.addLayout(self.cards_layout)

        panel = Panel(
            "Movimientos de inventario",
            "Haz doble clic en cualquier entrada o salida para corregirla. Las compras permiten controlar crédito y abonos.",
        )
        toolbar = QHBoxLayout()
        purchase = button("Registrar compra", "plus", "primary")
        consume = button("Registrar consumo", "materials")
        payment = button("Registrar abono", "money")
        edit_btn = button("Editar seleccionado", "edit")
        refresh_btn = button("Actualizar", "refresh")
        purchase.clicked.connect(lambda: self.movement("Compra"))
        consume.clicked.connect(lambda: self.movement("Consumo"))
        payment.clicked.connect(self.register_purchase_payment)
        edit_btn.clicked.connect(self.edit_movement)
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(payment)
        toolbar.addWidget(edit_btn)
        toolbar.addStretch()
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(consume)
        toolbar.addWidget(purchase)
        panel.body.addLayout(toolbar)
        self.table = QTableWidget()
        configure_table(
            self.table,
            [
                "Fecha", "Tipo", "Material", "Cantidad", "Litros", "Monto total",
                "Pagado", "Pendiente", "Estado pago", "Proveedor", "Marca", "Trabajo", "Notas",
            ],
        )
        self.table.doubleClicked.connect(self.edit_movement)
        panel.body.addWidget(self.table)
        layout.addWidget(panel, 1)
        self.refresh()

    def selected_movement_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def movement(self, kind: str) -> None:
        if MaterialMovementDialog(self.context, kind, self).exec():
            self.refresh()
            self.data_changed.emit()

    def edit_movement(self, *_args) -> None:
        movement_id = self.selected_movement_id()
        if not movement_id:
            QMessageBox.information(self, "Selecciona un movimiento", "Selecciona una compra o consumo para editarlo.")
            return
        row = self.repo.get_material_movement(movement_id)
        if not row:
            return
        if row["movement_type"] == "Venta" and row["sale_id"]:
            if MaterialSaleDialog(self.context, self, sale_id=int(row["sale_id"])).exec():
                self.refresh()
                self.data_changed.emit()
            return
        if MaterialMovementDialog(
            self.context,
            row["movement_type"],
            self,
            movement_id=movement_id,
        ).exec():
            self.refresh()
            self.data_changed.emit()

    def register_purchase_payment(self) -> None:
        movement_id = self.selected_movement_id()
        if not movement_id:
            QMessageBox.information(self, "Selecciona una compra", "Selecciona la compra a la que deseas registrar un abono.")
            return
        row = self.repo.get_material_movement(movement_id)
        if not row or row["movement_type"] != "Compra":
            QMessageBox.warning(self, "Movimiento no válido", "Los abonos solo pueden registrarse sobre compras.")
            return
        if float(row["balance_due"]) <= 0.005:
            QMessageBox.information(self, "Compra pagada", "Esta compra no tiene saldo pendiente.")
            return
        if PurchasePaymentDialog(self.context, movement_id, self).exec():
            self.refresh()
            self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "cards_layout"):
            return
        summary = self.repo.inventory_financial_summary()
        self.investment_card.set_value(currency(summary["stock_value"]))
        self.payable_card.set_value(currency(summary["payable"]))
        self.paid_card.set_value(currency(summary["paid"]))

        clear_layout(self.cards_layout)
        materials = self.repo.list_materials(True)
        for i, row in enumerate(materials):
            accent = "red" if float(row["stock_quantity"]) <= float(row["minimum_stock"]) else "blue"
            card = MetricCard(row["name"], "materials", accent)
            stock_value = float(row["stock_quantity"]) * float(row["average_unit_cost"])
            card.set_value(
                f"{float(row['stock_quantity']):.2f} {row['unit']}(s)",
                f"{float(row['stock_liters']):.2f} L · Valor actual {currency(stock_value)} · "
                f"Costo prom. {currency(row['average_unit_cost'])}"
                + (" · STOCK BAJO" if accent == "red" else ""),
            )
            self.cards_layout.addWidget(card, 0, i)

        rows = self.repo.material_movements(None, 500)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            is_purchase = row["movement_type"] == "Compra"
            is_sale = row["movement_type"] == "Venta"
            values = [
                format_date(row["movement_date"]), row["movement_type"], row["material"],
                f"{float(row['quantity']):.2f}", f"{float(row['liters']):.2f}",
                currency(row["total_cost"]), currency(row["amount_paid"]) if is_purchase else "—",
                currency(row["balance_due"]) if is_purchase else "—",
                row["payment_status"] if is_purchase else "No aplica",
                row["supplier"] or "—", row["brand"] or "—", row["job_code"] or "—", row["notes"],
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, row["id"])
                if c == 1:
                    item.setForeground(QColor("#15803d" if is_purchase else ("#2563eb" if is_sale else "#b45309")))
                if c == 8 and is_purchase:
                    item.setForeground(status_color(str(value)))
                self.table.setItem(r, c, item)


class MaterialSalesPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        metrics = QGridLayout()
        metrics.setSpacing(14)
        self.revenue_card = MetricCard("Ventas cobradas", "income", "green", "Dinero ingresado por venta de materiales")
        self.cost_card = MetricCard("Costo estimado vendido", "materials", "blue", "Costo promedio del inventario que salió")
        self.margin_card = MetricCard("Margen bruto estimado", "reports", "cyan", "Venta menos costo aproximado")
        metrics.addWidget(self.revenue_card, 0, 0)
        metrics.addWidget(self.cost_card, 0, 1)
        metrics.addWidget(self.margin_card, 0, 2)
        for column in range(3):
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        panel = Panel(
            "Venta de materiales",
            "Registra ventas directas de pintura o malla. El stock se descuenta y el dinero entra automáticamente en Caja.",
        )
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por cliente, material o comentario...")
        self.search.textChanged.connect(self.refresh)
        new_btn = button("Nueva venta", "plus", "primary")
        edit_btn = button("Editar seleccionada", "edit")
        delete_btn = button("Eliminar seleccionada", "delete")
        refresh_btn = button("Actualizar", "refresh")
        new_btn.clicked.connect(self.new_sale)
        edit_btn.clicked.connect(self.edit_sale)
        delete_btn.clicked.connect(self.delete_sale)
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(delete_btn)
        toolbar.addWidget(edit_btn)
        toolbar.addWidget(new_btn)
        panel.body.addLayout(toolbar)
        panel.body.addWidget(InfoBanner(
            "Cada venta se considera cobrada en el momento de guardarla. Si necesitas corregir cantidad, precio, fecha o cliente, haz doble clic sobre la venta; inventario y caja se recalculan.",
            "info",
        ))
        self.table = QTableWidget()
        configure_table(self.table, ["Fecha", "Cliente", "Materiales vendidos", "Venta", "Costo estimado", "Margen", "Comentario"])
        self.table.doubleClicked.connect(self.edit_sale)
        panel.body.addWidget(self.table)
        layout.addWidget(panel, 1)
        self.refresh()

    def selected_sale_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def new_sale(self) -> None:
        if MaterialSaleDialog(self.context, self).exec():
            self.refresh()
            self.data_changed.emit()

    def edit_sale(self, *_args) -> None:
        sale_id = self.selected_sale_id()
        if not sale_id:
            QMessageBox.information(self, "Selecciona una venta", "Selecciona la venta que deseas editar.")
            return
        if MaterialSaleDialog(self.context, self, sale_id=sale_id).exec():
            self.refresh()
            self.data_changed.emit()

    def delete_sale(self) -> None:
        sale_id = self.selected_sale_id()
        if not sale_id:
            QMessageBox.information(self, "Selecciona una venta", "Selecciona la venta que deseas eliminar.")
            return
        answer = QMessageBox.question(
            self,
            "Eliminar venta",
            "¿Eliminar esta venta? Los materiales volverán al inventario y el dinero se retirará del saldo de Caja.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repo.delete_material_sale(sale_id)
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo eliminar", str(exc))
            return
        self.refresh()
        self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        summary = self.repo.material_sales_summary()
        self.revenue_card.set_value(currency(summary["revenue"]))
        self.cost_card.set_value(currency(summary["cost"]))
        self.margin_card.set_value(currency(summary["margin"]))
        rows = self.repo.list_material_sales(self.search.text() if hasattr(self, "search") else "")
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            margin = float(row["total_amount"] or 0) - float(row["cost"] or 0)
            values = [
                format_date(row["sale_date"]), row["customer"] or "—", row["detail"] or "—",
                currency(row["total_amount"]), currency(row["cost"]), currency(margin), row["notes"] or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, int(row["id"]))
                if column == 5:
                    item.setForeground(QColor("#15803d" if margin >= 0 else "#b91c1c"))
                self.table.setItem(row_index, column, item)


class DebtsPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        metrics = QGridLayout()
        metrics.setSpacing(14)
        self.total_card = MetricCard("Deudas registradas", "expense", "blue", "Monto total original")
        self.paid_card = MetricCard("Pagado", "check", "green", "Abonos acumulados")
        self.pending_card = MetricCard("Pendiente", "warning", "red", "Saldo actual por pagar")
        metrics.addWidget(self.total_card, 0, 0)
        metrics.addWidget(self.paid_card, 0, 1)
        metrics.addWidget(self.pending_card, 0, 2)
        layout.addLayout(metrics)

        panel = Panel(
            "Deudas y pagos",
            "Las compras de materiales a crédito aparecen automáticamente. Las deudas personales o de otras empresas se registran aquí.",
        )
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar persona, empresa, material o nota…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.filter = QComboBox()
        self.filter.addItems(["Todas", "Pendientes", "Pagadas", "Materiales", "Personales / otras"])
        self.filter.currentTextChanged.connect(self.refresh)
        add = button("Nueva deuda", "plus", "primary")
        edit = button("Editar seleccionada", "edit")
        pay = button("Registrar pago", "money")
        refresh_btn = button("Actualizar", "refresh")
        add.clicked.connect(self.add_debt)
        edit.clicked.connect(self.edit_debt)
        pay.clicked.connect(self.pay_debt)
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.filter)
        toolbar.addWidget(pay)
        toolbar.addWidget(edit)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(add)
        panel.body.addLayout(toolbar)

        self.table = QTableWidget()
        configure_table(
            self.table,
            ["Fecha", "Persona / empresa", "Tipo", "Origen", "Monto total", "Pagado", "Pendiente", "Estado", "Notas"],
        )
        self.table.doubleClicked.connect(self.edit_debt)
        panel.body.addWidget(self.table)
        layout.addWidget(panel, 1)
        self.refresh()

    def selected_debt_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def add_debt(self) -> None:
        if DebtDialog(self.context, parent=self).exec():
            self.refresh()
            self.data_changed.emit()

    def edit_debt(self, *_args) -> None:
        debt_id = self.selected_debt_id()
        if not debt_id:
            QMessageBox.information(self, "Selecciona una deuda", "Selecciona una fila para editarla.")
            return
        if DebtDialog(self.context, debt_id, self).exec():
            self.refresh()
            self.data_changed.emit()

    def pay_debt(self) -> None:
        debt_id = self.selected_debt_id()
        if not debt_id:
            QMessageBox.information(self, "Selecciona una deuda", "Selecciona la deuda a la que deseas registrar un pago.")
            return
        row = self.repo.get_debt(debt_id)
        if not row or float(row["balance_due"]) <= 0.005:
            QMessageBox.information(self, "Deuda pagada", "Esta deuda no tiene saldo pendiente.")
            return
        if DebtPaymentDialog(self.context, debt_id, self).exec():
            self.refresh()
            self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        summary = self.repo.debt_summary()
        self.total_card.set_value(currency(summary["total"]))
        self.paid_card.set_value(currency(summary["paid"]))
        self.pending_card.set_value(currency(summary["pending"]))
        rows = self.repo.list_debts(self.filter.currentText(), self.search.text())
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            origin = f"Materiales · {row['material']}" if row["material_movement_id"] else "Registro manual"
            values = [
                format_date(row["debt_date"]), row["creditor"], row["debt_type"], origin,
                currency(row["total_amount"]), currency(row["amount_paid"]),
                currency(row["balance_due"]), row["payment_status"], row["notes"],
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value or "—"))
                if c == 0:
                    item.setData(Qt.UserRole, row["id"])
                if c == 7:
                    item.setForeground(status_color(str(value)))
                self.table.setItem(r, c, item)

class CashPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        metrics = QGridLayout()
        metrics.setSpacing(14)
        self.balance_card = MetricCard("Dinero en efectivo", "money", "green", "Saldo real según todos los movimientos")
        self.opening_card = MetricCard("Saldo inicial", "money", "blue", "Valor configurado como punto de partida")
        self.manual_in_card = MetricCard("Entradas manuales", "income", "cyan", "Aportes, regalos y otros ingresos de caja")
        self.manual_out_card = MetricCard("Salidas manuales", "expense", "red", "Retiros o ajustes no registrados en otras secciones")
        metrics.addWidget(self.balance_card, 0, 0)
        metrics.addWidget(self.opening_card, 0, 1)
        metrics.addWidget(self.manual_in_card, 0, 2)
        metrics.addWidget(self.manual_out_card, 0, 3)
        for c in range(4):
            metrics.setColumnStretch(c, 1)
        layout.addLayout(metrics)

        panel = Panel(
            "Libro de caja",
            "Aquí puedes auditar de dónde entra y sale el dinero. Los cobros, gastos, deudas, materiales, nómina y préstamos aparecen automáticamente.",
        )
        toolbar = QHBoxLayout()
        add_in = button("Registrar entrada", "plus", "primary")
        add_out = button("Registrar salida manual", "expense")
        edit = button("Editar seleccionado", "edit")
        delete = button("Eliminar seleccionado", "delete", "danger")
        refresh_btn = button("Actualizar", "refresh")
        add_in.clicked.connect(lambda: self.add_manual("Entrada"))
        add_out.clicked.connect(lambda: self.add_manual("Salida"))
        edit.clicked.connect(self.edit_selected)
        delete.clicked.connect(self.delete_selected)
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addStretch()
        toolbar.addWidget(delete)
        toolbar.addWidget(edit)
        toolbar.addWidget(add_out)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(add_in)
        panel.body.addLayout(toolbar)
        panel.body.addWidget(InfoBanner(
            "Selecciona cualquier entrada o salida para editarla o eliminarla. Caja modifica el registro original y recalcula sus saldos, reportes e inventario relacionados. Los cobros en el extranjero se marcan como ‘No’ en Efectivo y no aumentan Dinero en efectivo.",
            "info",
        ))

        self.table = QTableWidget()
        configure_table(self.table, ["Fecha", "Tipo", "Origen", "Concepto", "Entrada", "Salida", "Efectivo", "Comentario"])
        self.table.doubleClicked.connect(self.edit_selected)
        panel.body.addWidget(self.table)
        layout.addWidget(panel, 1)
        self.refresh()

    def selected_source(self) -> tuple[str, int] | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        source_type = self.table.item(row, 0).data(Qt.UserRole + 1)
        value = self.table.item(row, 0).data(Qt.UserRole)
        return (str(source_type), int(value)) if source_type and value else None

    def add_manual(self, direction: str) -> None:
        if CashMovementDialog(self.context, direction, self).exec():
            self.refresh()
            self.data_changed.emit()

    def edit_selected(self, *_args) -> None:
        selected = self.selected_source()
        if not selected:
            QMessageBox.information(self, "Selecciona un movimiento", "Selecciona una entrada o salida para editarla.")
            return
        source_type, source_id = selected
        dialog: QDialog | None = None
        if source_type == "manual":
            dialog = CashMovementDialog(self.context, parent=self, movement_id=source_id)
        elif source_type == "job_payment":
            payment = self.repo.payment(source_id)
            if payment:
                dialog = PaymentDialog(self.context, int(payment["job_id"]), self, payment_id=source_id)
        elif source_type == "expense":
            dialog = ExpenseDialog(self.context, self, expense_id=source_id)
        elif source_type == "material_sale":
            dialog = MaterialSaleDialog(self.context, self, sale_id=source_id)
        elif source_type == "material_payment":
            dialog = PaymentRecordDialog(self.context, "purchase", source_id, self)
        elif source_type == "material_purchase":
            row = self.repo.get_material_movement(source_id)
            if row:
                dialog = MaterialMovementDialog(self.context, str(row["movement_type"]), self, movement_id=source_id)
        elif source_type == "debt_payment":
            dialog = PaymentRecordDialog(self.context, "debt", source_id, self)
        elif source_type == "debt":
            dialog = DebtDialog(self.context, source_id, self)
        elif source_type == "loan":
            dialog = LoanDialog(self.context, source_id, self)
        elif source_type == "loan_payment":
            dialog = PaymentRecordDialog(self.context, "loan", source_id, self)
        elif source_type == "payroll":
            dialog = JobDetailDialog(self.context, source_id, self, on_saved=self.refresh)
        if dialog is None:
            QMessageBox.warning(self, "Movimiento no disponible", "El registro original ya no existe. Actualiza la lista.")
            self.refresh()
            return
        if dialog.exec():
            self.refresh()
            self.data_changed.emit()

    def delete_selected(self) -> None:
        selected = self.selected_source()
        if not selected:
            QMessageBox.information(self, "Selecciona un movimiento", "Selecciona una entrada o salida para eliminarla.")
            return
        source_type, source_id = selected
        descriptions = {
            "manual": "movimiento manual",
            "job_payment": "cobro del trabajo",
            "expense": "gasto",
            "material_sale": "venta de materiales",
            "material_payment": "abono de materiales",
            "material_purchase": "pago inicial de compra",
            "debt_payment": "pago de deuda",
            "debt": "pago inicial de deuda",
            "payroll": "nómina del trabajo",
            "loan": "préstamo y sus cobros asociados",
            "loan_payment": "cobro del préstamo",
        }
        description = descriptions.get(source_type, "movimiento")
        extra = (
            "\n\nLa nómina quedará en $0.00; el historial de trabajadores se conservará."
            if source_type == "payroll" else ""
        )
        answer = QMessageBox.question(
            self,
            "Eliminar movimiento",
            f"¿Eliminar este {description}?\n\nSe modificará su registro original y se recalculará Caja." + extra,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            if source_type == "manual":
                self.repo.delete_cash_movement(source_id)
            elif source_type == "job_payment":
                payment = self.repo.payment(source_id)
                if not payment:
                    raise ValueError("El cobro ya no existe.")
                self.repo.delete_payment(source_id, int(payment["job_id"]))
            elif source_type == "expense":
                self.repo.delete_expense(source_id)
            elif source_type == "material_sale":
                self.repo.delete_material_sale(source_id)
            elif source_type == "material_payment":
                self.repo.delete_purchase_payment(source_id)
            elif source_type == "material_purchase":
                self.repo.clear_purchase_legacy_payment(source_id)
            elif source_type == "debt_payment":
                self.repo.delete_debt_payment(source_id)
            elif source_type == "debt":
                self.repo.clear_debt_legacy_payment(source_id)
            elif source_type == "payroll":
                self.repo.clear_job_payroll(source_id)
            elif source_type == "loan":
                self.repo.delete_loan(source_id)
            elif source_type == "loan_payment":
                self.repo.delete_loan_repayment(source_id)
            else:
                raise ValueError("No se reconoce el origen del movimiento.")
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo eliminar", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo eliminar", str(exc))
            return
        self.refresh()
        self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        manual = self.repo.cash_manual_summary()
        self.balance_card.set_value(currency(self.repo.cash_balance()), "Incluye préstamos entregados y recuperados")
        self.opening_card.set_value(currency(self.repo.setting_float("cash_opening_balance", 0.0)))
        self.manual_in_card.set_value(currency(manual["incoming"]))
        self.manual_out_card.set_value(currency(manual["outgoing"]))
        rows = self.repo.cash_ledger()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            amount = float(row["amount"] or 0)
            values = [
                format_date(row["date"]), row["direction"], row["origin"], row["concept"],
                currency(amount) if row["direction"] == "Entrada" else "—",
                currency(amount) if row["direction"] == "Salida" else "—",
                "Sí" if row.get("affects_cash", True) else "No",
                row["notes"] or "—",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, row.get("source_id"))
                    item.setData(Qt.UserRole + 1, row.get("source_type"))
                if c == 4 and row["direction"] == "Entrada":
                    item.setForeground(QColor("#15803d"))
                if c == 5 and row["direction"] == "Salida":
                    item.setForeground(QColor("#b91c1c"))
                if c == 6 and not row.get("affects_cash", True):
                    item.setForeground(QColor("#b45309"))
                self.table.setItem(r, c, item)


class LoansPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        metrics = QGridLayout()
        metrics.setSpacing(14)
        self.total_card = MetricCard("Total prestado", "money", "blue", "Capital entregado registrado")
        self.repaid_card = MetricCard("Recuperado", "income", "green", "Dinero que ya te devolvieron")
        self.pending_card = MetricCard("Por cobrar", "warning", "amber", "Saldo que todavía te deben")
        metrics.addWidget(self.total_card, 0, 0)
        metrics.addWidget(self.repaid_card, 0, 1)
        metrics.addWidget(self.pending_card, 0, 2)
        for c in range(3):
            metrics.setColumnStretch(c, 1)
        layout.addLayout(metrics)

        loans_panel = Panel(
            "Préstamos realizados",
            "Prestar dinero reduce el efectivo, pero no se registra como gasto. Cada devolución aumenta el efectivo y reduce el saldo por cobrar.",
        )
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por persona o comentario…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.filter = QComboBox()
        self.filter.addItems(["Todos", "Pendientes", "Pagados"])
        self.filter.currentTextChanged.connect(self.refresh)
        add = button("Nuevo préstamo", "plus", "primary")
        edit = button("Editar", "edit")
        repay = button("Registrar cobro", "money")
        add.clicked.connect(self.add_loan)
        edit.clicked.connect(self.edit_loan)
        repay.clicked.connect(self.repay_loan)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.filter)
        toolbar.addWidget(repay)
        toolbar.addWidget(edit)
        toolbar.addWidget(add)
        loans_panel.body.addLayout(toolbar)

        self.table = QTableWidget()
        configure_table(self.table, ["Fecha", "Persona", "Prestado", "Cobrado", "Pendiente", "Estado", "Comentario"])
        self.table.doubleClicked.connect(self.edit_loan)
        self.table.itemSelectionChanged.connect(self.refresh_payment_history)
        self.table.setMinimumHeight(230)
        loans_panel.body.addWidget(self.table)
        layout.addWidget(loans_panel, 2)

        history = Panel("Cobros del préstamo seleccionado", "Cada abono conserva su fecha y comentario.")
        self.payment_table = QTableWidget()
        configure_table(self.payment_table, ["Fecha", "Monto recibido", "Comentario"])
        self.payment_table.setMinimumHeight(150)
        history.body.addWidget(self.payment_table)
        layout.addWidget(history, 1)
        self.refresh()

    def selected_loan_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def add_loan(self) -> None:
        if LoanDialog(self.context, parent=self).exec():
            self.refresh()
            self.data_changed.emit()

    def edit_loan(self, *_args) -> None:
        loan_id = self.selected_loan_id()
        if not loan_id:
            QMessageBox.information(self, "Selecciona un préstamo", "Selecciona una fila para editarla.")
            return
        if LoanDialog(self.context, loan_id, self).exec():
            self.refresh()
            self.data_changed.emit()

    def repay_loan(self) -> None:
        loan_id = self.selected_loan_id()
        if not loan_id:
            QMessageBox.information(self, "Selecciona un préstamo", "Selecciona primero a la persona que te pagó.")
            return
        loan = self.repo.get_loan(loan_id)
        if not loan or float(loan["balance_due"] or 0) <= 0.005:
            QMessageBox.information(self, "Préstamo pagado", "Este préstamo ya no tiene saldo pendiente.")
            return
        if LoanRepaymentDialog(self.context, loan_id, self).exec():
            self.refresh()
            self.data_changed.emit()

    def refresh_payment_history(self) -> None:
        if not hasattr(self, "payment_table"):
            return
        loan_id = self.selected_loan_id()
        rows = self.repo.loan_repayments(loan_id) if loan_id else []
        self.payment_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate([format_date(row["payment_date"]), currency(row["amount"]), row["notes"] or "—"]):
                self.payment_table.setItem(r, c, QTableWidgetItem(str(value)))

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        selected = self.selected_loan_id()
        summary = self.repo.loan_summary()
        self.total_card.set_value(currency(summary["total"]))
        self.repaid_card.set_value(currency(summary["repaid"]))
        self.pending_card.set_value(currency(summary["pending"]))
        rows = self.repo.list_loans(self.search.text(), self.filter.currentText())
        self.table.setRowCount(len(rows))
        selected_row = -1
        for r, row in enumerate(rows):
            values = [
                format_date(row["loan_date"]), row["borrower"], currency(row["total_amount"]),
                currency(row["repaid"]), currency(row["balance_due"]), row["payment_status"], row["notes"] or "—",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, row["id"])
                if c == 5:
                    item.setForeground(status_color(str(value)))
                self.table.setItem(r, c, item)
            if selected and int(row["id"]) == selected:
                selected_row = r
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        elif rows:
            self.table.selectRow(0)
        self.refresh_payment_history()


class IncomesPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.total_card = MetricCard("Ingresos registrados", "income", "green")
        layout.addWidget(self.total_card)
        panel = Panel("Historial de cobros", "Anticipos, pagos parciales y pagos finales asociados a trabajos.")
        toolbar = QHBoxLayout()
        edit = button("Editar seleccionado", "edit")
        delete = button("Eliminar seleccionado", "delete", "danger")
        edit.clicked.connect(self.edit_payment)
        delete.clicked.connect(self.delete_payment)
        toolbar.addStretch()
        toolbar.addWidget(delete)
        toolbar.addWidget(edit)
        panel.body.addLayout(toolbar)
        self.table = QTableWidget()
        configure_table(self.table, ["Fecha", "Trabajo", "Cliente", "Tipo", "Monto", "Propina", "Notas"])
        self.table.doubleClicked.connect(self.edit_payment)
        panel.body.addWidget(self.table)
        layout.addWidget(panel, 1)
        self.refresh()

    def selected_payment_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def edit_payment(self, *_args) -> None:
        payment_id = self.selected_payment_id()
        if not payment_id:
            QMessageBox.information(self, "Selecciona un cobro", "Selecciona el cobro que deseas editar.")
            return
        payment = self.repo.payment(payment_id)
        if not payment:
            self.refresh()
            return
        if PaymentDialog(self.context, int(payment["job_id"]), self, payment_id=payment_id).exec():
            self.refresh()
            self.data_changed.emit()

    def delete_payment(self) -> None:
        payment_id = self.selected_payment_id()
        if not payment_id:
            QMessageBox.information(self, "Selecciona un cobro", "Selecciona el cobro que deseas eliminar.")
            return
        payment = self.repo.payment(payment_id)
        if not payment:
            self.refresh()
            return
        answer = QMessageBox.question(
            self,
            "Eliminar cobro",
            f"¿Eliminar el cobro de {currency(payment['amount'])}?\n\nCaja y el saldo pendiente del trabajo se recalcularán.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repo.delete_payment(payment_id, int(payment["job_id"]))
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo eliminar", str(exc))
            return
        self.refresh()
        self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        rows = self.repo.payments()
        total = sum(float(row["amount"]) for row in rows)
        self.total_card.set_value(currency(total), f"{len(rows)} cobro(s) registrados")
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                format_date(row["payment_date"]), row["code"], row["client"], row["payment_type"],
                currency(row["amount"]), currency(row["tip_amount"] or 0), row["notes"],
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, int(row["id"]))
                self.table.setItem(r, c, item)


class ExpensesPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.total_card = MetricCard("Gastos generales registrados", "expense", "red")
        layout.addWidget(self.total_card)
        panel = Panel("Historial de gastos", "Gastos generales y gastos asociados a trabajos.")
        toolbar = QHBoxLayout()
        add = button("Registrar gasto", "plus", "primary")
        edit = button("Editar seleccionado", "edit")
        delete = button("Eliminar seleccionado", "delete", "danger")
        add.clicked.connect(self.add_expense)
        edit.clicked.connect(self.edit_expense)
        delete.clicked.connect(self.delete_expense)
        toolbar.addStretch()
        toolbar.addWidget(delete)
        toolbar.addWidget(edit)
        toolbar.addWidget(add)
        panel.body.addLayout(toolbar)
        self.table = QTableWidget()
        configure_table(self.table, ["Fecha", "Descripción", "Categoría", "Trabajo", "Monto"])
        self.table.doubleClicked.connect(self.edit_expense)
        panel.body.addWidget(self.table)
        layout.addWidget(panel, 1)
        self.refresh()

    def add_expense(self) -> None:
        if ExpenseDialog(self.context, self).exec():
            self.refresh()
            self.data_changed.emit()

    def selected_expense_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def edit_expense(self, *_args) -> None:
        expense_id = self.selected_expense_id()
        if not expense_id:
            QMessageBox.information(self, "Selecciona un gasto", "Selecciona el gasto que deseas editar.")
            return
        if ExpenseDialog(self.context, self, expense_id=expense_id).exec():
            self.refresh()
            self.data_changed.emit()

    def delete_expense(self) -> None:
        expense_id = self.selected_expense_id()
        if not expense_id:
            QMessageBox.information(self, "Selecciona un gasto", "Selecciona el gasto que deseas eliminar.")
            return
        expense = self.repo.get_expense(expense_id)
        if not expense:
            self.refresh()
            return
        answer = QMessageBox.question(
            self,
            "Eliminar gasto",
            f"¿Eliminar el gasto “{expense['description']}” por {currency(expense['amount'])}?\n\nCaja y los reportes se recalcularán.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repo.delete_expense(expense_id)
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo eliminar", str(exc))
            return
        self.refresh()
        self.data_changed.emit()

    def refresh(self) -> None:
        if not hasattr(self, "table"):
            return
        rows = self.repo.expenses()
        total = sum(float(row["amount"]) for row in rows)
        self.total_card.set_value(currency(total), f"{len(rows)} gasto(s) registrados")
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                format_date(row["expense_date"]), row["description"], row["category"],
                row["code"] or "—", currency(row["amount"]),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, int(row["id"]))
                self.table.setItem(r, c, item)


class ReportsPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        content.setObjectName("PageContent")
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 6)
        layout.setSpacing(14)
        layout.addWidget(
            InfoBanner(
                "Los mantenimientos se muestran para control operativo, pero no se suman a los metros de rendimiento de las brigadas ni de los trabajadores.",
                "info",
            )
        )
        crews = Panel("Resumen por brigada")
        self.crew_table = QTableWidget()
        configure_table(
            self.crew_table,
            ["Brigada", "Trabajos", "Metros desde cero", "Mantenimiento registrado", "Monto acordado", "Nómina"],
        )
        self.crew_table.setMinimumHeight(220)
        crews.body.addWidget(self.crew_table)
        layout.addWidget(crews)
        workers = Panel("Participación por trabajador")
        self.worker_table = QTableWidget()
        configure_table(
            self.worker_table,
            ["Trabajador", "Trabajos participados", "Metros desde cero", "Pago acumulado"],
        )
        self.worker_table.setMinimumHeight(220)
        workers.body.addWidget(self.worker_table)
        layout.addWidget(workers)
        self.refresh()

    def refresh(self) -> None:
        if not hasattr(self, "crew_table"):
            return
        crews = self.repo.crew_report()
        self.crew_table.setRowCount(len(crews))
        for r, row in enumerate(crews):
            values = [
                row["name"], row["jobs_count"], f"{float(row['new_area']):.2f} m²",
                f"{float(row['maintenance_area']):.2f} m²", currency(row["amount"]),
                currency(row["payroll"]),
            ]
            for c, value in enumerate(values):
                self.crew_table.setItem(r, c, QTableWidgetItem(str(value)))
        workers = self.repo.worker_report()
        self.worker_table.setRowCount(len(workers))
        for r, row in enumerate(workers):
            values = [
                row["name"], row["jobs_count"], f"{float(row['meters']):.2f} m²",
                currency(row["pay"]),
            ]
            for c, value in enumerate(values):
                self.worker_table.setItem(r, c, QTableWidgetItem(str(value)))


class FinancialReportsPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)

        # Esta pantalla puede contener métricas, gráfica y tablas al mismo
        # tiempo. El scroll mantiene alturas legibles en 1080p y con escalado.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        content.setObjectName("PageContent")
        scroll.setWidget(content)
        outer.addWidget(scroll)

        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 6, 6)
        root.setSpacing(14)

        controls = Panel(
            "Período del análisis",
            "Selecciona un mes, un año o cualquier rango de varios meses. Después puedes exportarlo a PDF para imprimir.",
        )
        fields = QGridLayout()
        fields.setHorizontalSpacing(10)
        fields.setVerticalSpacing(10)
        self.preset = QComboBox()
        self.preset.addItems(["Mes actual", "Año actual", "Rango personalizado"])
        self.start_date = make_date_edit()
        self.end_date = make_date_edit()
        fields.addWidget(QLabel("Período rápido"), 0, 0)
        fields.addWidget(self.preset, 0, 1)
        fields.addWidget(QLabel("Desde"), 0, 2)
        fields.addWidget(self.start_date, 0, 3)
        fields.addWidget(QLabel("Hasta"), 0, 4)
        fields.addWidget(self.end_date, 0, 5)
        fields.setColumnStretch(6, 1)
        controls.body.addLayout(fields)

        actions = QHBoxLayout()
        actions.addStretch()
        apply_btn = button("Analizar período", "reports", "primary")
        export_btn = button("Crear PDF", "copy")
        actions.addWidget(apply_btn)
        actions.addWidget(export_btn)
        controls.body.addLayout(actions)
        root.addWidget(controls)
        self.preset.currentTextChanged.connect(self.apply_preset)
        apply_btn.clicked.connect(self.refresh)
        export_btn.clicked.connect(self.export_pdf)

        metrics = QGridLayout()
        metrics.setSpacing(14)
        self.report_cash = MetricCard("Dinero en efectivo", "money", "green", "Saldo actual acumulado")
        self.report_income = MetricCard("Entradas del período", "income", "cyan", "Todo el efectivo que realmente entró")
        self.report_expenses = MetricCard("Salidas del período", "expense", "red", "Todo el efectivo que realmente salió")
        self.report_profit = MetricCard("Flujo neto", "reports", "blue")
        self.report_debt = MetricCard("Deudas pendientes", "expense", "amber")
        metrics.addWidget(self.report_cash, 0, 0)
        metrics.addWidget(self.report_income, 0, 1)
        metrics.addWidget(self.report_expenses, 0, 2)
        metrics.addWidget(self.report_profit, 1, 0)
        metrics.addWidget(self.report_debt, 1, 1)
        for column in range(3):
            metrics.setColumnStretch(column, 1)
        root.addLayout(metrics)

        # Gráfica y detalle comparten una fila. La tabla tiene altura reservada
        # para mostrar al menos 4-5 conceptos sin redimensionar la ventana.
        analysis_grid = QGridLayout()
        analysis_grid.setSpacing(14)
        chart_panel = Panel("Flujo de caja por mes")
        chart_panel.body.addWidget(InfoBanner(
            "Las barras muestran todas las Entradas y Salidas reales de caja. Los aportes externos y cobros de préstamos aparecen como entradas; los préstamos entregados aparecen como salidas.",
            "info",
        ))
        self.chart = FinancialChart()
        chart_panel.body.addWidget(self.chart)

        detail = Panel("Detalle financiero del período")
        self.detail_table = QTableWidget()
        configure_table(self.detail_table, ["Concepto", "Monto"])
        self.detail_table.setMinimumWidth(300)
        self.detail_table.setMinimumHeight(250)
        self.detail_table.setMaximumHeight(300)
        self.detail_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        detail.body.addWidget(self.detail_table)

        analysis_grid.addWidget(chart_panel, 0, 0)
        analysis_grid.addWidget(detail, 0, 1)
        analysis_grid.setColumnStretch(0, 2)
        analysis_grid.setColumnStretch(1, 1)
        root.addLayout(analysis_grid)

        self.apply_preset("Mes actual")
        self.refresh()

    def apply_preset(self, preset: str) -> None:
        today = date.today()
        if preset == "Mes actual":
            start = date(today.year, today.month, 1)
            end = date(today.year, today.month, monthrange(today.year, today.month)[1])
        elif preset == "Año actual":
            start = date(today.year, 1, 1)
            end = date(today.year, 12, 31)
        else:
            return
        self.start_date.setDate(QDate(start.year, start.month, start.day))
        self.end_date.setDate(QDate(end.year, end.month, end.day))

    def selected_range(self) -> tuple[str, str]:
        start = self.start_date.date()
        end = self.end_date.date()
        if start > end:
            start, end = end, start
        return start.toString("yyyy-MM-dd"), end.toString("yyyy-MM-dd")

    def refresh(self) -> None:
        if not hasattr(self, "detail_table"):
            return
        start, end = self.selected_range()
        self.current_summary = self.repo.financial_summary(start, end)
        self.current_series = self.repo.financial_series(start, end, "month")
        summary = self.current_summary
        self.report_cash.set_value(currency(summary["cash_balance"]), "Disponible real según movimientos registrados")
        self.report_income.set_value(currency(summary["cash_inflows"]))
        self.report_expenses.set_value(currency(summary["expenses"]))
        self.report_profit.set_value(currency(summary["profit"]))
        self.report_debt.set_value(currency(summary["debt_balance"]), "Saldo actual, no solo del período")
        self.chart.set_series(self.current_series)
        details = [
            ("Dinero en efectivo actual", summary["cash_balance"]),
            ("Cobros de trabajos", summary["job_income"]),
            ("Cobros en el extranjero (no efectivo)", summary["foreign_job_income"]),
            ("Ventas de materiales", summary["material_sales"]),
            ("Otras entradas de caja", summary["manual_inflows"]),
            ("Cobros de préstamos", summary["loan_repayments"]),
            ("Total de entradas de efectivo", summary["cash_inflows"]),
            ("Gastos generales pagados", summary["general_expenses"]),
            ("Pagos realizados por materiales", summary["material_payments"]),
            ("Pagos de otras deudas", summary["debt_payments"]),
            ("Nómina de trabajos finalizados", summary["payroll"]),
            ("Préstamos entregados", summary["loans_issued"]),
            ("Otras salidas manuales", summary["manual_outflows"]),
            ("Total de salidas de efectivo", summary["expenses"]),
            ("Flujo neto del período", summary["profit"]),
            ("Flujo operativo (sin préstamos/aportes)", summary["operating_cash_net"]),
            ("Compras de materiales registradas", summary["material_purchases"]),
            ("Valor actual del inventario", summary["inventory_value"]),
            ("Deudas pendientes actuales", summary["debt_balance"]),
            ("Préstamos por cobrar actuales", summary["loans_receivable_balance"]),
        ]
        self.detail_table.setRowCount(len(details))
        for row_index, (label, value) in enumerate(details):
            self.detail_table.setItem(row_index, 0, QTableWidgetItem(label))
            item = QTableWidgetItem(currency(value))
            if label == "Flujo neto del período":
                item.setForeground(QColor("#15803d" if value >= 0 else "#b91c1c"))
            self.detail_table.setItem(row_index, 1, item)

    def export_pdf(self) -> None:
        self.refresh()
        start, end = self.selected_range()
        default = f"reporte_financiero_{start}_a_{end}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar reporte financiero", default, "Documento PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            create_financial_report(
                path,
                start_date=start,
                end_date=end,
                summary=self.current_summary,
                series=self.current_series,
                expense_categories=self.repo.expense_category_summary(start, end),
                income_jobs=self.repo.income_by_job(start, end),
                pending_debts=self.repo.pending_debts(1000),
            )
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo crear el PDF", str(exc))
            return
        QMessageBox.information(self, "Reporte creado", f"El reporte se guardó en:\n{path}")


class SettingsPage(RefreshablePage):
    def __init__(self, context: ApplicationContext, parent=None) -> None:
        super().__init__(context, parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        content.setObjectName("PageContent")
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QGridLayout(content)
        self.settings_layout = layout
        layout.setContentsMargins(0, 0, 6, 6)
        layout.setSpacing(16)

        defaults = Panel("Valores por defecto", "Precios, rendimiento de materiales y alertas.")
        form = QFormLayout()
        form.setVerticalSpacing(11)
        self.fields: dict[str, FlexibleDoubleSpinBox | QSpinBox] = {}

        def decimal(key: str, label: str, value: float, suffix: str = "") -> None:
            field = FlexibleDoubleSpinBox()
            field.setRange(0, 10_000_000)
            field.setDecimals(2)
            field.setValue(value)
            field.setSuffix(suffix)
            field.setButtonSymbols(QAbstractSpinBox.NoButtons)
            form.addRow(label, field)
            self.fields[key] = field

        decimal("price_new", "Precio desde cero", self.repo.setting_float("price_new", 10), " USD/m²")
        decimal("price_maintenance", "Precio mantenimiento", self.repo.setting_float("price_maintenance", 6), " USD/m²")
        decimal("cash_opening_balance", "Efectivo inicial del negocio", self.repo.setting_float("cash_opening_balance", 0), " USD")
        decimal("paint_coverage_m2", "Rendimiento pintura", self.repo.setting_float("paint_coverage_m2", 25), " m²/cubeta")
        decimal("mesh_roll_coverage_m2", "Rendimiento malla", self.repo.setting_float("mesh_roll_coverage_m2", 100), " m²/rollo")
        years = QSpinBox()
        years.setRange(1, 20)
        years.setButtonSymbols(QAbstractSpinBox.NoButtons)
        years.setValue(self.repo.setting_int("maintenance_years", 3))
        form.addRow("Años para mantenimiento", years)
        self.fields["maintenance_years"] = years
        warning = QSpinBox()
        warning.setRange(0, 365)
        warning.setButtonSymbols(QAbstractSpinBox.NoButtons)
        warning.setValue(self.repo.setting_int("maintenance_warning_days", 90))
        warning.setSuffix(" días")
        form.addRow("Avisar con anticipación", warning)
        self.fields["maintenance_warning_days"] = warning
        defaults.body.addLayout(form)
        defaults.body.addWidget(InfoBanner(
            "Efectivo inicial = dinero que ya tenías disponible antes del primer movimiento registrado en D&Y Finanzas. "
            "El Dashboard suma los cobros y resta únicamente los pagos que realmente salieron de caja.",
            "info",
        ))

        rates = Panel("Tarifas salariales por m²", "Reglas base utilizadas al generar la nómina.")
        rates_form = QFormLayout()
        rates_form.setVerticalSpacing(11)
        self.rate_fields: dict[str, FlexibleDoubleSpinBox] = {}
        rate_specs = [
            ("rate_crew1_leader_new", "Jefe brigada 1", 0.7),
            ("rate_crew2_leader_new", "Jefe brigada 2", 0.6),
            ("rate_helper_new", "Ayudantes", 0.5),
            ("rate_partner_new", "Socio", 0.7),
            ("rate_admin_crew2_new", "Administrador de brigada 2", 0.3),
            ("rate_maintenance", "Todos en mantenimiento", 0.3),
        ]
        for key, label, default in rate_specs:
            field = FlexibleDoubleSpinBox()
            field.setRange(0, 100)
            field.setDecimals(2)
            field.setButtonSymbols(QAbstractSpinBox.NoButtons)
            field.setValue(self.repo.setting_float(key, default))
            field.setSuffix(" USD/m²")
            rates_form.addRow(label, field)
            self.rate_fields[key] = field
        rates.body.addLayout(rates_form)

        appearance = Panel("Apariencia", "Ajusta el tamaño de las letras y el tema visual de toda la aplicación.")
        appearance_form = QFormLayout()
        self.font_size = QComboBox()
        for increment in range(0, 7):
            label = "Tamaño normal" if increment == 0 else f"Aumentar {increment} punto(s)"
            self.font_size.addItem(label, increment)
        current_increment = self.repo.setting_int("font_size_increment", 0)
        self.font_size.setCurrentIndex(max(self.font_size.findData(current_increment), 0))
        appearance_form.addRow("Tamaño de letra", self.font_size)
        self.theme = QComboBox()
        self.theme.addItems(THEME_NAMES)
        current_theme = self.repo.setting("theme_name", "Claro")
        self.theme.setCurrentText(current_theme if current_theme in THEME_NAMES else "Claro")
        appearance_form.addRow("Tema", self.theme)
        appearance.body.addLayout(appearance_form)
        appearance.body.addWidget(InfoBanner("El cambio se aplica al guardar. Si algún diálogo ya estaba abierto, ciérralo y vuelve a abrirlo.", "info"))

        database_panel = Panel("Base de datos", "Crea una copia en la carpeta que elijas o importa una base de datos anterior.")
        database_panel.body.addWidget(InfoBanner(f"Base activa: {self.repo.database_path}", "info"))
        backup_btn = button("Guardar copia en una carpeta", "copy")
        import_btn = button("Importar base de datos", "refresh")
        backup_btn.clicked.connect(self.backup_to_directory)
        import_btn.clicked.connect(self.import_database)
        database_panel.body.addWidget(backup_btn)
        database_panel.body.addWidget(import_btn)
        database_panel.body.addStretch()

        save_btn = button("Guardar configuración", "save", "primary")
        save_btn.clicked.connect(self.save)
        database_panel.body.addWidget(save_btn)

        self.settings_panels = [defaults, rates, appearance, database_panel]
        self._arrange_panels()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._arrange_panels()

    def _arrange_panels(self) -> None:
        if not hasattr(self, "settings_panels"):
            return
        for panel in self.settings_panels:
            self.settings_layout.removeWidget(panel)
        increment = self.repo.setting_int("font_size_increment", 0)
        single_column = self.width() < 980 + (increment * 30)
        if single_column:
            for row, panel in enumerate(self.settings_panels):
                self.settings_layout.addWidget(panel, row, 0)
            self.settings_layout.setColumnStretch(0, 1)
            self.settings_layout.setColumnStretch(1, 0)
        else:
            self.settings_layout.addWidget(self.settings_panels[0], 0, 0)
            self.settings_layout.addWidget(self.settings_panels[1], 0, 1)
            self.settings_layout.addWidget(self.settings_panels[2], 1, 0)
            self.settings_layout.addWidget(self.settings_panels[3], 1, 1)
            self.settings_layout.setColumnStretch(0, 1)
            self.settings_layout.setColumnStretch(1, 1)

    def save(self) -> None:
        values: dict[str, Any] = {}
        values.update({key: field.value() for key, field in self.fields.items()})
        values.update({key: field.value() for key, field in self.rate_fields.items()})
        increment = int(self.font_size.currentData())
        values["font_size_increment"] = increment
        theme_name = self.theme.currentText()
        values["theme_name"] = theme_name
        self.repo.save_settings(values)
        app = QApplication.instance()
        if app:
            from PySide6.QtCore import QTimer
            from PySide6.QtGui import QFont
            app.setProperty("theme_name", theme_name)
            app.setFont(QFont("Segoe UI", 10 + increment))
            app.setStyleSheet(build_app_style(increment, theme_name))
            for window in app.topLevelWidgets():
                refresh_adaptive_metrics(window)
                refresh_layout = getattr(window, "refresh_font_layout", None)
                if callable(refresh_layout):
                    refresh_layout()
            QTimer.singleShot(0, lambda: [
                refresh_adaptive_metrics(window) for window in app.topLevelWidgets()
            ])
            QTimer.singleShot(0, self._arrange_panels)
        QMessageBox.information(self, "Configuración guardada", "Los valores se guardaron correctamente.")
        self.data_changed.emit()

    def backup_to_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta para la copia")
        if not directory:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = Path(directory) / f"dy_finanzas_backup_{stamp}.db"
        self.repo.backup(destination)
        QMessageBox.information(self, "Copia creada", f"La copia se guardó en:\n{destination}")

    def import_database(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar base de datos", "", "Base de datos (*.db);;Todos los archivos (*)")
        if not path:
            return
        answer = QMessageBox.question(
            self, "Confirmar importación",
            "La base actual será reemplazada. Antes se creará una copia automática junto a la base activa. ¿Continuar?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            safety = self.repo.database_path.with_name(
                f"dy_finanzas_antes_de_importar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            )
            self.repo.backup(safety)
            self.context.database.restore(path)
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo importar", str(exc))
            return
        QMessageBox.information(self, "Base importada", f"La base se importó correctamente.\nCopia de seguridad: {safety}")
        self.data_changed.emit()
