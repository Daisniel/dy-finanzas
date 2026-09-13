from __future__ import annotations

from typing import Any, Callable, Mapping

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .context import ApplicationContext
from .formatters import format_date, round_area
from .icons import icon
from .services import MeasurementTotals, PayrollLine
from .ui_components import FlexibleDoubleSpinBox, InfoBanner, MetricCard, Panel, button, configure_table


def _date_edit(value: str | None = None) -> QDateEdit:
    widget = QDateEdit()
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("dd/MM/yyyy")
    if value:
        parsed = QDate.fromString(value, "yyyy-MM-dd")
        widget.setDate(parsed if parsed.isValid() else QDate.currentDate())
    else:
        widget.setDate(QDate.currentDate())
    return widget


def _money_spin(value: float = 0.0, maximum: float = 1_000_000.0) -> FlexibleDoubleSpinBox:
    widget = FlexibleDoubleSpinBox()
    widget.setRange(-maximum, maximum)
    widget.setDecimals(2)
    widget.setPrefix("$ ")
    widget.setValue(value)
    widget.setButtonSymbols(QAbstractSpinBox.NoButtons)
    return widget


class ClientEditDialog(QDialog):
    def __init__(self, context: ApplicationContext, client_id: int, parent=None) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.client_id = client_id
        row = self.repo.get_client(client_id)
        if not row:
            raise ValueError("Cliente no encontrado")
        self.setWindowTitle("Editar cliente")
        self.setMinimumWidth(560)
        panel = Panel(
            "Información del cliente",
            "Los cambios se reflejan en todos los trabajos relacionados.",
        )
        self.name = QLineEdit(row["name"] or "")
        self.phone = QLineEdit(row["phone"] or "")
        self.address = QTextEdit(row["address"] or "")
        self.address.setMaximumHeight(95)
        self.notes = QTextEdit(row["notes"] or "")
        self.notes.setMaximumHeight(95)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Nombre", self.name)
        form.addRow("Teléfono(s)", self.phone)
        form.addRow("Dirección", self.address)
        form.addRow("Notas", self.notes)
        panel.body.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar cambios")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Dato requerido", "Escribe el nombre del cliente.")
            return
        self.repo.save_client(
            name,
            self.phone.text().strip(),
            self.address.toPlainText().strip(),
            self.notes.toPlainText().strip(),
            self.client_id,
        )
        self.accept()


class WorkerDialog(QDialog):
    def __init__(
        self,
        context: ApplicationContext,
        worker_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.repo = context.repository
        self.worker_id = worker_id
        self.setWindowTitle("Editar trabajador" if worker_id else "Nuevo trabajador")
        self.setMinimumWidth(480)

        panel = Panel(
            "Datos del trabajador",
            "La brigada y el rol habitual pueden cambiarse para un trabajo específico.",
        )
        self.name = QLineEdit()
        self.name.setPlaceholderText("Nombre completo")
        self.crew = QComboBox()
        self.crew.addItem("Sin brigada", None)
        for row in self.repo.active_crews():
            self.crew.addItem(row["name"], row["id"])
        self.role = QComboBox()
        self.role.setEditable(True)
        self.role.addItems(["Jefe / Administrador", "Jefe", "Ayudante", "Socio", "Otro"])
        self.partner = QCheckBox("Es el socio")
        self.active = QCheckBox("Trabajador activo")
        self.active.setChecked(True)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.addRow("Nombre", self.name)
        form.addRow("Brigada habitual", self.crew)
        form.addRow("Rol habitual", self.role)
        form.addRow("", self.partner)
        form.addRow("", self.active)
        panel.body.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

        if worker_id:
            row = self.repo.get_worker(worker_id)
            if row:
                self.name.setText(row["name"])
                idx = self.crew.findData(row["base_crew_id"])
                self.crew.setCurrentIndex(max(idx, 0))
                self.role.setCurrentText(row["base_role"])
                self.partner.setChecked(bool(row["is_partner"]))
                self.active.setChecked(bool(row["active"]))

    def save(self) -> None:
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Dato requerido", "Escribe el nombre del trabajador.")
            return
        try:
            self.repo.save_worker(
                {
                    "name": name,
                    "base_crew_id": self.crew.currentData(),
                    "base_role": self.role.currentText().strip(),
                    "is_partner": self.partner.isChecked(),
                    "active": self.active.isChecked(),
                },
                self.worker_id,
            )
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.accept()


class ExpenseDialog(QDialog):
    def __init__(
        self,
        context: ApplicationContext,
        parent=None,
        expense_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.repo = context.repository
        self.expense_id = expense_id
        existing = self.repo.get_expense(expense_id) if expense_id else None
        if expense_id and not existing:
            raise ValueError("Gasto no encontrado")
        self.setWindowTitle("Editar gasto" if expense_id else "Registrar gasto")
        self.setMinimumWidth(500)

        panel = Panel(
            "Editar gasto" if expense_id else "Nuevo gasto",
            "Registra gastos generales o asociados a un trabajo.",
        )
        self.date = _date_edit(existing["expense_date"] if existing else None)
        self.description = QLineEdit(str(existing["description"] or "") if existing else "")
        self.description.setPlaceholderText("Ej.: combustible, transporte, herramienta…")
        self.amount = _money_spin(float(existing["amount"] or 0) if existing else 0)
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(["General", "Materiales", "Transporte", "Herramientas", "Reparación", "Otro"])
        if existing:
            self.category.setCurrentText(str(existing["category"] or "General"))
        self.job = QComboBox()
        self.job.addItem("Sin trabajo asociado", None)
        for row in self.repo.jobs_for_combo():
            self.job.addItem(f"{row['code']} — {row['client']}", row["id"])
        if existing:
            index = self.job.findData(existing["job_id"])
            self.job.setCurrentIndex(max(index, 0))

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha", self.date)
        form.addRow("Descripción", self.description)
        form.addRow("Monto", self.amount)
        form.addRow("Categoría", self.category)
        form.addRow("Trabajo", self.job)
        panel.body.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar cambios" if expense_id else "Registrar gasto")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        if not self.description.text().strip() or self.amount.value() <= 0:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Indica una descripción y un monto mayor que cero.",
            )
            return
        try:
            self.repo.save_expense(
                self.date.date().toString("yyyy-MM-dd"),
                self.description.text().strip(),
                self.amount.value(),
                self.category.currentText().strip(),
                self.job.currentData(),
                self.expense_id,
            )
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.accept()


class CashMovementDialog(QDialog):
    def __init__(
        self,
        context: ApplicationContext,
        direction: str = "Entrada",
        parent=None,
        movement_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.movement_id = movement_id
        existing = self.repo.get_cash_movement(movement_id) if movement_id else None
        self.setWindowTitle("Editar movimiento de caja" if movement_id else "Registrar movimiento de caja")
        self.setMinimumWidth(540)

        panel = Panel(
            "Movimiento de caja",
            "Úsalo para dinero que entra o sale y que no pertenece a cobros de trabajos, gastos, deudas o materiales ya registrados.",
        )
        self.date = _date_edit(existing["movement_date"] if existing else None)
        self.direction = QComboBox()
        self.direction.addItems(["Entrada", "Salida"])
        self.direction.setCurrentText(str(existing["direction"] if existing else direction))
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems([
            "Aporte de otro negocio",
            "Regalo / aporte personal",
            "Dinero recuperado",
            "Ajuste de caja",
            "Retiro personal",
            "Otro",
        ])
        if existing:
            self.category.setCurrentText(str(existing["category"] or "Otro"))
        self.amount = _money_spin(float(existing["amount"] or 0) if existing else 0)
        self.amount.setMinimum(0.01)
        self.notes = QTextEdit(str(existing["notes"] or "") if existing else "")
        self.notes.setMaximumHeight(100)
        self.notes.setPlaceholderText("Ej.: Me transfirieron $500 desde el otro negocio")

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha", self.date)
        form.addRow("Tipo", self.direction)
        form.addRow("Concepto", self.category)
        form.addRow("Monto", self.amount)
        form.addRow("Comentario", self.notes)
        panel.body.addLayout(form)
        panel.body.addWidget(InfoBanner(
            "Si el dinero corresponde al pago de un préstamo que registraste en Préstamos, usa allí ‘Registrar cobro’ para no contabilizarlo dos veces.",
            "info",
        ))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar movimiento")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        try:
            self.repo.save_cash_movement(
                self.date.date().toString("yyyy-MM-dd"),
                self.direction.currentText(),
                self.category.currentText().strip(),
                self.amount.value(),
                self.notes.toPlainText().strip(),
                self.movement_id,
            )
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.accept()


class LoanDialog(QDialog):
    def __init__(self, context: ApplicationContext, loan_id: int | None = None, parent=None) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.loan_id = loan_id
        existing = self.repo.get_loan(loan_id) if loan_id else None
        self.setWindowTitle("Editar préstamo" if loan_id else "Nuevo préstamo")
        self.setMinimumWidth(540)

        panel = Panel(
            "Dinero prestado",
            "Registrar un préstamo reduce el dinero en efectivo, pero no se considera un gasto del negocio.",
        )
        self.borrower = QLineEdit(str(existing["borrower"] or "") if existing else "")
        self.borrower.setPlaceholderText("Persona a quien le prestaste")
        self.date = _date_edit(existing["loan_date"] if existing else None)
        self.amount = _money_spin(float(existing["total_amount"] or 0) if existing else 0)
        self.amount.setMinimum(0.01)
        self.notes = QTextEdit(str(existing["notes"] or "") if existing else "")
        self.notes.setMaximumHeight(100)
        self.notes.setPlaceholderText("Motivo, acuerdo, forma de devolución, etc.")

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("A quién", self.borrower)
        form.addRow("Fecha del préstamo", self.date)
        form.addRow("Monto", self.amount)
        form.addRow("Comentario", self.notes)
        panel.body.addLayout(form)
        if existing and float(existing["repaid"] or 0) > 0:
            panel.body.addWidget(InfoBanner(
                f"Ya se han cobrado ${float(existing['repaid']):,.2f}. El total del préstamo no puede reducirse por debajo de esa cantidad.",
                "info",
            ))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar préstamo")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        try:
            self.repo.save_loan(
                self.borrower.text().strip(),
                self.date.date().toString("yyyy-MM-dd"),
                self.amount.value(),
                self.notes.toPlainText().strip(),
                self.loan_id,
            )
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.accept()


class LoanRepaymentDialog(QDialog):
    def __init__(self, context: ApplicationContext, loan_id: int, parent=None) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.loan_id = loan_id
        loan = self.repo.get_loan(loan_id)
        if not loan:
            raise ValueError("Préstamo no encontrado")
        self.balance = float(loan["balance_due"] or 0)
        self.setWindowTitle("Registrar cobro de préstamo")
        self.setMinimumWidth(520)

        panel = Panel(
            f"Cobro de {loan['borrower']}",
            f"Saldo pendiente actual: ${self.balance:,.2f}",
        )
        self.date = _date_edit()
        self.amount = _money_spin(self.balance, maximum=max(self.balance, 1_000_000))
        self.amount.setMinimum(0.01)
        self.amount.setMaximum(max(self.balance, 0.01))
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Ej.: Abono en efectivo")
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha", self.date)
        form.addRow("Monto recibido", self.amount)
        form.addRow("Comentario", self.notes)
        panel.body.addLayout(form)
        panel.body.addWidget(InfoBanner(
            "Este cobro aumenta automáticamente el dinero en efectivo y reduce el saldo que te deben.",
            "success",
        ))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Registrar cobro")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        try:
            self.repo.add_loan_repayment(
                self.loan_id,
                self.date.date().toString("yyyy-MM-dd"),
                self.amount.value(),
                self.notes.text().strip(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo registrar", str(exc))
            return
        self.accept()


class PaymentRecordDialog(QDialog):
    """Edit one linked payment record from Caja without breaking its source link."""

    _CONFIG = {
        "purchase": (
            "get_purchase_payment",
            "update_purchase_payment",
            "Editar abono de materiales",
            "Abono a proveedor",
            "El importe se actualizará también en el saldo de la compra y su deuda.",
        ),
        "debt": (
            "get_debt_payment",
            "update_debt_payment",
            "Editar pago de deuda",
            "Pago a deuda",
            "El importe se actualizará también en el saldo pendiente de la deuda.",
        ),
        "loan": (
            "get_loan_repayment",
            "update_loan_repayment",
            "Editar cobro de préstamo",
            "Cobro de préstamo",
            "El importe se actualizará también en el saldo por cobrar.",
        ),
    }

    def __init__(self, context: ApplicationContext, kind: str, payment_id: int, parent=None) -> None:
        super().__init__(parent)
        if kind not in self._CONFIG:
            raise ValueError("Tipo de pago no compatible")
        self.repo = context.repository
        self.kind = kind
        self.payment_id = payment_id
        getter, _updater, title, heading, help_text = self._CONFIG[kind]
        row = getattr(self.repo, getter)(payment_id)
        if not row:
            raise ValueError("El movimiento ya no existe")
        self.setWindowTitle(title)
        self.setMinimumWidth(500)

        party = ""
        if kind == "purchase":
            party = str(row["supplier"] or row["material"] or "Proveedor")
        elif kind == "debt":
            party = str(row["creditor"] or "Acreedor")
        else:
            party = str(row["borrower"] or "Persona")
        panel = Panel(heading, party)
        self.date = _date_edit(str(row["payment_date"]))
        self.amount = _money_spin(float(row["amount"] or 0))
        self.amount.setMinimum(0.01)
        self.notes = QLineEdit(str(row["notes"] or ""))
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha", self.date)
        form.addRow("Monto", self.amount)
        form.addRow("Comentario", self.notes)
        panel.body.addLayout(form)
        panel.body.addWidget(InfoBanner(help_text, "info"))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar cambios")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        _getter, updater, _title, _heading, _help = self._CONFIG[self.kind]
        try:
            getattr(self.repo, updater)(
                self.payment_id,
                self.date.date().toString("yyyy-MM-dd"),
                self.amount.value(),
                self.notes.text().strip(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Movimiento no válido", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.accept()


class MaterialSaleDialog(QDialog):
    """Register or edit a cash sale of one or more inventory materials."""

    def __init__(
        self,
        context: ApplicationContext,
        parent=None,
        sale_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.sale_id = sale_id
        self.sale = self.repo.get_material_sale(sale_id) if sale_id else None
        if sale_id and not self.sale:
            raise ValueError("Venta no encontrada")
        self.items: list[dict[str, Any]] = []
        self.original_quantities: dict[int, float] = {}
        if sale_id:
            for row in self.repo.material_sale_items(sale_id):
                material_id = int(row["material_id"])
                quantity = float(row["quantity"] or 0)
                self.original_quantities[material_id] = self.original_quantities.get(material_id, 0.0) + quantity
                self.items.append({
                    "material_id": material_id,
                    "material": str(row["material"]),
                    "unit": str(row["unit"]),
                    "quantity": quantity,
                    "unit_price": float(row["unit_price"] or 0),
                })

        self.setWindowTitle("Editar venta de materiales" if sale_id else "Nueva venta de materiales")
        self.setMinimumWidth(760)
        self.resize(820, 650)
        panel = Panel(
            "Venta de materiales",
            "La venta descuenta el inventario inmediatamente y el importe entra en Caja como efectivo recibido.",
        )
        self.date = _date_edit(self.sale["sale_date"] if self.sale else None)
        self.customer = QLineEdit(self.sale["customer"] if self.sale else "")
        self.customer.setPlaceholderText("Nombre del cliente (opcional)")
        self.notes = QLineEdit(self.sale["notes"] if self.sale else "")
        self.notes.setPlaceholderText("Comentario o referencia de la venta")
        header_form = QFormLayout()
        header_form.setVerticalSpacing(10)
        header_form.addRow("Fecha", self.date)
        header_form.addRow("Cliente", self.customer)
        header_form.addRow("Comentario", self.notes)
        panel.body.addLayout(header_form)

        line_panel = Panel("Agregar material", "Puedes vender pintura de 16 L, 19 L y malla en la misma operación.")
        line_grid = QGridLayout()
        line_grid.setHorizontalSpacing(10)
        line_grid.setVerticalSpacing(8)
        self.material = QComboBox()
        for row in self.repo.list_materials(True):
            self.material.addItem(
                row["name"],
                (int(row["id"]), float(row["stock_quantity"] or 0), str(row["unit"]),
                 float(row["average_unit_cost"] or 0), float(row["package_size"] or 0), str(row["category"])),
            )
        self.quantity = FlexibleDoubleSpinBox()
        self.quantity.setRange(0.01, 100_000)
        self.quantity.setDecimals(2)
        self.quantity.setValue(1)
        self.quantity.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.unit_price = _money_spin()
        self.stock_label = QLabel()
        self.stock_label.setObjectName("Muted")
        self.line_total = QLabel("Total de línea: $0.00")
        self.line_total.setObjectName("MetricSubtitle")
        add_line = button("Agregar / actualizar línea", "plus", "primary")
        remove_line = button("Quitar seleccionado", "delete")
        add_line.clicked.connect(self.add_or_update_line)
        remove_line.clicked.connect(self.remove_selected_line)
        self.material.currentIndexChanged.connect(self.material_changed)
        self.quantity.valueChanged.connect(self.update_line_total)
        self.unit_price.valueChanged.connect(self.update_line_total)
        line_grid.addWidget(QLabel("Material"), 0, 0)
        line_grid.addWidget(self.material, 0, 1, 1, 3)
        line_grid.addWidget(QLabel("Cantidad"), 1, 0)
        line_grid.addWidget(self.quantity, 1, 1)
        line_grid.addWidget(QLabel("Precio de venta / unidad"), 1, 2)
        line_grid.addWidget(self.unit_price, 1, 3)
        line_grid.addWidget(self.stock_label, 2, 0, 1, 2)
        line_grid.addWidget(self.line_total, 2, 2, 1, 2)
        line_grid.addWidget(remove_line, 3, 2)
        line_grid.addWidget(add_line, 3, 3)
        line_panel.body.addLayout(line_grid)
        panel.body.addWidget(line_panel)

        self.table = QTableWidget()
        configure_table(self.table, ["Material", "Disponible", "Cantidad", "Precio/unidad", "Total"])
        self.table.setMinimumHeight(190)
        self.table.doubleClicked.connect(self.load_selected_line)
        panel.body.addWidget(self.table)
        self.total_label = QLabel("Total a cobrar: $0.00")
        self.total_label.setObjectName("MetricValue")
        self.total_label.setAlignment(Qt.AlignRight)
        panel.body.addWidget(self.total_label)
        panel.body.addWidget(InfoBanner(
            "Al guardar, el stock se descuenta y el total de la venta aumenta Dinero en efectivo. Si editas o eliminas la venta, inventario y Caja se corrigen automáticamente.",
            "info",
        ))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar venta")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(panel)
        layout.addWidget(buttons)
        self.material_changed()
        self.refresh_items()

    def available_for_sale(self, material_id: int) -> float:
        for index in range(self.material.count()):
            data = self.material.itemData(index)
            if data and int(data[0]) == int(material_id):
                return float(data[1]) + float(self.original_quantities.get(material_id, 0.0))
        return float(self.original_quantities.get(material_id, 0.0))

    def material_changed(self, *_args) -> None:
        data = self.material.currentData()
        if not data:
            return
        material_id, _stock, unit, average_cost, _size, _category = data
        available = self.available_for_sale(int(material_id))
        self.stock_label.setText(
            f"Disponible para esta venta: {available:g} {unit}(s) · Costo prom.: ${float(average_cost or 0):,.2f}"
        )
        existing = next((item for item in self.items if int(item["material_id"]) == int(material_id)), None)
        if existing:
            self.quantity.setValue(float(existing["quantity"]))
            self.unit_price.setValue(float(existing["unit_price"]))
        else:
            self.quantity.setValue(1 if available >= 1 else max(available, 0.01))
            self.unit_price.setValue(0)
        self.update_line_total()

    def update_line_total(self, *_args) -> None:
        self.line_total.setText(f"Total de línea: ${self.quantity.value() * self.unit_price.value():,.2f}")

    def add_or_update_line(self) -> None:
        data = self.material.currentData()
        if not data:
            return
        material_id, _stock, unit, _average_cost, _size, _category = data
        quantity = float(self.quantity.value())
        if self.unit_price.value() <= 0:
            QMessageBox.warning(self, "Precio requerido", "Escribe un precio de venta por unidad mayor que cero.")
            return
        available = self.available_for_sale(int(material_id))
        if quantity > available + 0.0001:
            QMessageBox.warning(
                self, "Stock insuficiente",
                f"Solo hay {available:g} {unit}(s) disponibles para esta venta.",
            )
            return
        payload = {
            "material_id": int(material_id),
            "material": self.material.currentText(),
            "unit": str(unit),
            "quantity": quantity,
            "unit_price": float(self.unit_price.value()),
        }
        for index, item in enumerate(self.items):
            if int(item["material_id"]) == int(material_id):
                self.items[index] = payload
                break
        else:
            self.items.append(payload)
        self.refresh_items()

    def selected_item_index(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        value = self.table.item(row, 0).data(Qt.UserRole)
        if value is None:
            return None
        material_id = int(value)
        for index, item in enumerate(self.items):
            if int(item["material_id"]) == material_id:
                return index
        return None

    def load_selected_line(self, *_args) -> None:
        index = self.selected_item_index()
        if index is None:
            return
        item = self.items[index]
        # Select the matching material manually; item data is a metadata tuple.
        for i in range(self.material.count()):
            data = self.material.itemData(i)
            if data and int(data[0]) == int(item["material_id"]):
                self.material.setCurrentIndex(i)
                break
        self.quantity.setValue(float(item["quantity"]))
        self.unit_price.setValue(float(item["unit_price"]))

    def remove_selected_line(self) -> None:
        index = self.selected_item_index()
        if index is None:
            QMessageBox.information(self, "Selecciona una línea", "Selecciona el material que deseas quitar de la venta.")
            return
        del self.items[index]
        self.refresh_items()

    def refresh_items(self) -> None:
        self.table.setRowCount(len(self.items))
        total = 0.0
        for row_index, item in enumerate(self.items):
            available = self.available_for_sale(int(item["material_id"]))
            line_total = float(item["quantity"]) * float(item["unit_price"])
            total += line_total
            values = [
                item["material"], f"{available:g} {item['unit']}(s)", f"{float(item['quantity']):.2f}",
                f"${float(item['unit_price']):,.2f}", f"${line_total:,.2f}",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 0:
                    cell.setData(Qt.UserRole, int(item["material_id"]))
                self.table.setItem(row_index, column, cell)
        self.total_label.setText(f"Total a cobrar: ${total:,.2f}")

    def save(self) -> None:
        if not self.items:
            QMessageBox.warning(self, "Venta vacía", "Agrega al menos un material a la venta.")
            return
        try:
            self.repo.save_material_sale(
                sale_date=self.date.date().toString("yyyy-MM-dd"),
                customer=self.customer.text().strip(),
                items=self.items,
                notes=self.notes.text().strip(),
                sale_id=self.sale_id,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo guardar la venta", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar la venta", str(exc))
            return
        self.accept()


class MaterialMovementDialog(QDialog):
    def __init__(
        self,
        context: ApplicationContext,
        movement_type: str | None = None,
        parent=None,
        movement_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.repo = context.repository
        self.movement_id = movement_id
        self.existing = self.repo.get_material_movement(movement_id) if movement_id else None
        self.movement_type = str(self.existing["movement_type"] if self.existing else movement_type or "Compra")
        self._syncing = False
        self.setWindowTitle("Editar movimiento" if movement_id else f"Registrar {self.movement_type.lower()}")
        self.setMinimumWidth(620)

        title = "Editar movimiento de inventario" if movement_id else (
            "Entrada de material" if self.movement_type == "Compra" else "Consumo de material"
        )
        subtitle = (
            "Registra si la compra fue pagada, quedó a crédito o tuvo un pago parcial."
            if self.movement_type == "Compra"
            else "El consumo se descuenta del inventario y puede asociarse a un trabajo."
        )
        panel = Panel(title, subtitle)
        self.date = _date_edit()
        self.material = QComboBox()
        for row in self.repo.list_materials(True):
            self.material.addItem(
                row["name"],
                (row["id"], row["package_size"], row["average_unit_cost"], row["category"]),
            )
        self.quantity = FlexibleDoubleSpinBox()
        self.quantity.setRange(0.01, 100_000)
        self.quantity.setDecimals(2)
        self.quantity.setValue(1)
        self.quantity.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.liters = FlexibleDoubleSpinBox()
        self.liters.setRange(0, 1_000_000)
        self.liters.setDecimals(2)
        self.liters.setSuffix(" L")
        self.liters.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.liters.setReadOnly(True)
        self.liters.setToolTip("Se calcula automáticamente según la cantidad y la presentación del material.")
        self.unit_cost = _money_spin()
        self.total_cost = _money_spin()
        self.supplier = QLineEdit()
        self.supplier.setPlaceholderText("Empresa o proveedor")
        self.brand = QLineEdit()
        self.brand.setPlaceholderText("Marca de la pintura o malla")
        self.payment_mode = QComboBox()
        self.payment_mode.addItems(["Pagado", "Pendiente", "Pago parcial"])
        self.amount_paid = _money_spin()
        self.balance_label = QLabel("Saldo pendiente: $0.00")
        self.balance_label.setObjectName("Muted")
        self.job = QComboBox()
        self.job.addItem("Sin trabajo asociado", None)
        for row in self.repo.jobs_for_combo():
            self.job.addItem(f"{row['code']} — {row['client']}", row["id"])
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Observación opcional")

        self.material.currentIndexChanged.connect(self.suggest_values)
        self.quantity.valueChanged.connect(self.recalculate_total)
        self.unit_cost.valueChanged.connect(self.recalculate_total)
        self.total_cost.valueChanged.connect(self.total_changed)
        self.payment_mode.currentTextChanged.connect(self.payment_mode_changed)
        self.amount_paid.valueChanged.connect(self.update_balance)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha", self.date)
        form.addRow("Material", self.material)
        form.addRow("Cantidad", self.quantity)
        form.addRow("Litros equivalentes", self.liters)
        form.addRow("Costo unitario", self.unit_cost)
        form.addRow("Monto total", self.total_cost)
        if self.movement_type == "Compra":
            form.addRow("Proveedor", self.supplier)
            form.addRow("Marca", self.brand)
            form.addRow("Condición de pago", self.payment_mode)
            form.addRow("Pagado hasta ahora", self.amount_paid)
            form.addRow("", self.balance_label)
        else:
            form.addRow("Trabajo asociado", self.job)
        form.addRow("Observaciones", self.notes)
        panel.body.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar cambios" if movement_id else "Registrar")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

        self.suggest_values()
        if self.existing:
            self.load_existing()
        else:
            self.payment_mode_changed(self.payment_mode.currentText())

    def load_existing(self) -> None:
        row = self.existing
        self._syncing = True
        parsed = QDate.fromString(row["movement_date"], "yyyy-MM-dd")
        if parsed.isValid():
            self.date.setDate(parsed)
        for index in range(self.material.count()):
            data = self.material.itemData(index)
            if data and int(data[0]) == int(row["material_id"]):
                self.material.setCurrentIndex(index)
                break
        self.quantity.setValue(float(row["quantity"]))
        self.liters.setValue(float(row["liters"]))
        self.unit_cost.setValue(float(row["unit_cost"]))
        self.total_cost.setValue(float(row["total_cost"]))
        self.supplier.setText(row["supplier"] or "")
        self.brand.setText(row["brand"] or "")
        if self.movement_type == "Compra":
            status = row["payment_status"] or "Pendiente"
            self.payment_mode.setCurrentText(status if status in {"Pagado", "Pendiente", "Pago parcial"} else "Pendiente")
            self.amount_paid.setValue(float(row["amount_paid"]))
        else:
            idx = self.job.findData(row["job_id"])
            self.job.setCurrentIndex(max(idx, 0))
        self.notes.setText(row["notes"] or "")
        self._syncing = False
        if self.movement_type == "Compra":
            self.payment_mode_changed(self.payment_mode.currentText())
        self.update_balance()

    def suggest_values(self) -> None:
        data = self.material.currentData()
        if not data or self._syncing:
            return
        _material_id, package_size, average_cost, category = data
        if self.movement_type in {"Consumo", "Devolución"} and float(average_cost) > 0:
            self.unit_cost.setValue(float(average_cost))
        self._set_derived_liters(package_size, category)
        self.recalculate_total()

    def _set_derived_liters(self, package_size: float | None = None, category: str | None = None) -> None:
        data = self.material.currentData()
        if data and (package_size is None or category is None):
            _material_id, package_size, _average_cost, category = data
        if str(category) == "Pintura":
            self.liters.setValue(self.quantity.value() * float(package_size or 0))
        else:
            self.liters.setValue(0)

    def recalculate_total(self) -> None:
        if self._syncing:
            return
        data = self.material.currentData()
        if data:
            _material_id, package_size, _average_cost, category = data
            self._set_derived_liters(package_size, category)
        self._syncing = True
        self.total_cost.setValue(round(self.quantity.value() * self.unit_cost.value(), 2))
        self._syncing = False
        if self.movement_type == "Compra":
            self.payment_mode_changed(self.payment_mode.currentText())
        self.update_balance()

    def total_changed(self) -> None:
        if self._syncing:
            return
        if self.quantity.value() > 0:
            self._syncing = True
            self.unit_cost.setValue(self.total_cost.value() / self.quantity.value())
            self._syncing = False
        if self.movement_type == "Compra":
            self.payment_mode_changed(self.payment_mode.currentText())
        self.update_balance()

    def payment_mode_changed(self, mode: str) -> None:
        if self.movement_type != "Compra" or self._syncing:
            return
        if mode == "Pagado":
            self.amount_paid.setEnabled(False)
            self.amount_paid.setValue(self.total_cost.value())
        elif mode == "Pendiente":
            self.amount_paid.setEnabled(False)
            self.amount_paid.setValue(0)
        else:
            self.amount_paid.setEnabled(True)
            if self.amount_paid.value() >= self.total_cost.value():
                self.amount_paid.setValue(0)
        self.update_balance()

    def update_balance(self) -> None:
        if self.movement_type != "Compra":
            return
        balance = max(self.total_cost.value() - self.amount_paid.value(), 0)
        self.balance_label.setText(f"Saldo pendiente: ${balance:,.2f}")

    def save(self) -> None:
        data = self.material.currentData()
        if not data:
            return
        material_id, _package_size, _average_cost, _category = data
        if self.movement_type == "Compra" and self.amount_paid.value() > self.total_cost.value() + 0.005:
            QMessageBox.warning(self, "Monto inválido", "Lo pagado no puede superar el total de la compra.")
            return
        try:
            if self.movement_id:
                self.repo.update_material_movement(
                    self.movement_id,
                    movement_date=self.date.date().toString("yyyy-MM-dd"),
                    material_id=int(material_id),
                    quantity=self.quantity.value(),
                    liters=self.liters.value(),
                    unit_cost=self.unit_cost.value(),
                    total_cost=self.total_cost.value(),
                    job_id=self.job.currentData() if self.movement_type in {"Consumo", "Devolución"} else None,
                    notes=self.notes.text().strip(),
                    supplier=self.supplier.text().strip(),
                    brand=self.brand.text().strip(),
                    target_paid=self.amount_paid.value(),
                )
            else:
                self.repo.record_material_movement(
                    movement_date=self.date.date().toString("yyyy-MM-dd"),
                    material_id=int(material_id),
                    movement_type=self.movement_type,
                    quantity=self.quantity.value(),
                    liters=self.liters.value(),
                    unit_cost=self.unit_cost.value(),
                    total_cost=self.total_cost.value(),
                    job_id=self.job.currentData() if self.movement_type in {"Consumo", "Devolución"} else None,
                    notes=self.notes.text().strip(),
                    supplier=self.supplier.text().strip(),
                    brand=self.brand.text().strip(),
                    payment_mode=self.payment_mode.currentText(),
                    amount_paid=self.amount_paid.value(),
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Movimiento no válido", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.accept()


class PurchasePaymentDialog(QDialog):
    def __init__(self, context: ApplicationContext, movement_id: int, parent=None) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.movement_id = movement_id
        row = self.repo.get_material_movement(movement_id)
        if not row or row["movement_type"] != "Compra":
            raise ValueError("Compra no encontrada")
        self.row = row
        balance = max(float(row["total_cost"]) - float(row["amount_paid"]), 0)
        self.setWindowTitle("Registrar abono a proveedor")
        self.setMinimumWidth(500)
        panel = Panel(
            "Abono de materiales",
            f"{row['material']} · Proveedor: {row['supplier'] or 'Sin especificar'}",
        )
        panel.body.addWidget(
            InfoBanner(
                f"Total ${float(row['total_cost']):,.2f} · Pagado ${float(row['amount_paid']):,.2f} · Pendiente ${balance:,.2f}",
                "info",
            )
        )
        self.date = _date_edit()
        self.amount = _money_spin(balance)
        self.amount.setRange(0.01, max(balance, 0.01))
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Transferencia, efectivo, referencia, etc.")
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha", self.date)
        form.addRow("Monto del abono", self.amount)
        form.addRow("Notas", self.notes)
        panel.body.addLayout(form)

        history_label = QLabel("Historial de pagos de esta compra")
        history_label.setObjectName("PanelTitle")
        panel.body.addWidget(history_label)
        self.history_table = QTableWidget()
        configure_table(self.history_table, ["Fecha", "Monto", "Notas"])
        self.history_table.setMinimumHeight(170)
        history = self.repo.purchase_payments(self.movement_id)
        self.history_table.setRowCount(len(history))
        for r, payment in enumerate(history):
            values = [format_date(payment["payment_date"]), f"${float(payment['amount']):,.2f}", payment["notes"]]
            for c, value in enumerate(values):
                self.history_table.setItem(r, c, QTableWidgetItem(str(value)))
        panel.body.addWidget(self.history_table)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Registrar abono")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        try:
            self.repo.add_purchase_payment(
                self.movement_id,
                self.date.date().toString("yyyy-MM-dd"),
                self.amount.value(),
                self.notes.text().strip(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Abono no válido", str(exc))
            return
        self.accept()


class DebtDialog(QDialog):
    def __init__(
        self,
        context: ApplicationContext,
        debt_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.debt_id = debt_id
        self.row = self.repo.get_debt(debt_id) if debt_id else None
        self.setWindowTitle("Editar deuda" if debt_id else "Registrar deuda")
        self.setMinimumWidth(590)

        linked = bool(self.row and self.row["material_movement_id"])
        panel = Panel(
            "Editar deuda" if debt_id else "Nueva deuda",
            "Las compras de materiales a crédito se enlazan automáticamente con este apartado."
            if not linked
            else "Esta deuda está vinculada a una compra de materiales; los cambios se reflejarán en ambos apartados.",
        )
        self.date = _date_edit(self.row["debt_date"] if self.row else None)
        self.creditor = QLineEdit(self.row["creditor"] if self.row else "")
        self.creditor.setPlaceholderText("Persona o empresa")
        self.debt_type = QComboBox()
        self.debt_type.setEditable(True)
        self.debt_type.addItems(["Personal", "Proveedor", "Préstamo", "Materiales", "Otra"])
        if self.row:
            self.debt_type.setCurrentText(self.row["debt_type"] or "Otra")
        self.total = _money_spin(float(self.row["total_amount"]) if self.row else 0)
        self.paid = _money_spin(float(self.row["amount_paid"]) if self.row else 0)
        self.balance = QLabel("Saldo pendiente: $0.00")
        self.balance.setObjectName("Muted")
        self.notes = QTextEdit(self.row["notes"] if self.row else "")
        self.notes.setMaximumHeight(95)
        self.total.valueChanged.connect(self.update_balance)
        self.paid.valueChanged.connect(self.update_balance)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha de la deuda", self.date)
        form.addRow("Persona o empresa", self.creditor)
        form.addRow("Tipo", self.debt_type)
        form.addRow("Monto total", self.total)
        form.addRow("Pagado hasta ahora", self.paid)
        form.addRow("", self.balance)
        form.addRow("Notas", self.notes)
        panel.body.addLayout(form)
        if linked:
            panel.body.addWidget(InfoBanner("Vinculada a una compra de materiales.", "info"))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar cambios" if debt_id else "Registrar deuda")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)
        self.update_balance()

    def update_balance(self) -> None:
        self.paid.setMaximum(max(self.total.value(), 0.0))
        balance = max(self.total.value() - self.paid.value(), 0.0)
        self.balance.setText(f"Saldo pendiente: ${balance:,.2f}")

    def save(self) -> None:
        if not self.creditor.text().strip():
            QMessageBox.warning(self, "Dato requerido", "Indica la persona o empresa a la que se debe.")
            return
        if self.total.value() <= 0:
            QMessageBox.warning(self, "Monto inválido", "El monto total debe ser mayor que cero.")
            return
        try:
            self.repo.save_debt(
                creditor=self.creditor.text().strip(),
                debt_date=self.date.date().toString("yyyy-MM-dd"),
                total_amount=self.total.value(),
                amount_paid=self.paid.value(),
                debt_type=self.debt_type.currentText().strip() or "Otra",
                notes=self.notes.toPlainText().strip(),
                debt_id=self.debt_id,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo guardar", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.accept()


class DebtPaymentDialog(QDialog):
    def __init__(self, context: ApplicationContext, debt_id: int, parent=None) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.debt_id = debt_id
        self.row = self.repo.get_debt(debt_id)
        if not self.row:
            raise ValueError("Deuda no encontrada")
        balance = float(self.row["balance_due"])
        self.setWindowTitle("Registrar pago de deuda")
        self.setMinimumWidth(560)
        panel = Panel(
            "Pago de deuda",
            f"{self.row['creditor']} · Saldo pendiente ${balance:,.2f}",
        )
        self.date = _date_edit()
        self.amount = _money_spin(balance)
        self.amount.setRange(0.01, max(balance, 0.01))
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Transferencia, efectivo, referencia, etc.")
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha", self.date)
        form.addRow("Monto pagado", self.amount)
        form.addRow("Notas", self.notes)
        panel.body.addLayout(form)

        history = self.repo.debt_payments(debt_id)
        table = QTableWidget()
        configure_table(table, ["Fecha", "Monto", "Origen", "Notas"])
        table.setMinimumHeight(170)
        table.setRowCount(len(history))
        for r, payment in enumerate(history):
            values = [
                format_date(payment["payment_date"]),
                f"${float(payment['amount']):,.2f}",
                payment["source"],
                payment["notes"],
            ]
            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(str(value)))
        panel.body.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Registrar pago")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        try:
            self.repo.add_debt_payment(
                self.debt_id,
                self.date.date().toString("yyyy-MM-dd"),
                self.amount.value(),
                self.notes.text().strip(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Pago no válido", str(exc))
            return
        self.accept()


class PaymentDialog(QDialog):
    def __init__(
        self,
        context: ApplicationContext,
        job_id: int,
        parent=None,
        payment_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.repo = context.repository
        self.job_id = job_id
        self.payment_id = payment_id
        row = self.repo.payment(payment_id, job_id) if payment_id else None
        if payment_id and not row:
            raise ValueError("Cobro no encontrado")
        self.setWindowTitle("Editar cobro" if payment_id else "Registrar cobro")
        self.setMinimumWidth(470)

        panel = Panel(
            "Editar cobro" if payment_id else "Nuevo cobro",
            "Registra anticipos, pagos parciales o el pago final. Los cobros en el extranjero quedan visibles en Caja para auditoría, pero no aumentan el efectivo local.",
        )
        self.date = _date_edit(row["payment_date"] if row else None)
        self.payment_type = QComboBox()
        payment_types = [
            "Anticipo", "Pago parcial", "Pago final", "Cobro",
            "Pago parcial en el extranjero", "Pago final en el extranjero",
        ]
        if row and row["payment_type"] not in payment_types:
            payment_types.append(str(row["payment_type"]))
        self.payment_type.addItems(payment_types)
        if row:
            self.payment_type.setCurrentText(row["payment_type"])
        total = float(row["amount"] or 0) if row else 0.0
        tip = float(row["tip_amount"] or 0) if row else 0.0
        self.amount = _money_spin(max(total - tip, 0.0), max(1_000_000.0, total))
        self.tip = _money_spin(tip, max(1_000_000.0, tip))
        self.notes = QLineEdit(row["notes"] or "" if row else "")
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Fecha", self.date)
        form.addRow("Tipo", self.payment_type)
        form.addRow("Monto", self.amount)
        form.addRow("Propina", self.tip)
        form.addRow("Notas", self.notes)
        panel.body.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Registrar cobro")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addWidget(buttons)

    def save(self) -> None:
        if self.amount.value() <= 0:
            QMessageBox.warning(self, "Monto inválido", "El monto debe ser mayor que cero.")
            return
        try:
            values = (
                self.date.date().toString("yyyy-MM-dd"),
                self.payment_type.currentText(),
                self.amount.value(),
                self.notes.text().strip(),
                self.tip.value(),
            )
            if self.payment_id:
                self.repo.update_payment(
                    self.payment_id,
                    self.job_id,
                    values[0],
                    values[1],
                    values[2],
                    values[3],
                    tip_amount=values[4],
                )
            else:
                self.repo.add_payment(
                    self.job_id,
                    values[0],
                    values[1],
                    values[2],
                    values[3],
                    tip_amount=values[4],
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Cobro no válido", str(exc))
            return
        self.accept()


class QuotePreviewDialog(QDialog):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Presupuesto para WhatsApp")
        self.resize(720, 690)
        panel = Panel(
            "Vista previa del presupuesto",
            "Puedes editar el mensaje antes de copiarlo en WhatsApp.",
        )
        # Use plain text explicitly. QTextEdit(text) can route the string
        # through rich-text parsing, which collapses the newline separators
        # when the quote is displayed and copied to WhatsApp.
        self.editor = QTextEdit()
        self.editor.setPlainText(text)
        self.editor.setMinimumHeight(500)
        panel.body.addWidget(self.editor)
        copy_button = button("Copiar al portapapeles", "copy", "primary")
        close_button = button("Cerrar")
        copy_button.clicked.connect(self.copy_to_clipboard)
        close_button.clicked.connect(self.accept)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(close_button)
        actions.addWidget(copy_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(panel)
        layout.addLayout(actions)

    def copy_to_clipboard(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.editor.toPlainText())
        QMessageBox.information(
            self,
            "Presupuesto copiado",
            "El mensaje se copió al portapapeles y está listo para pegar en WhatsApp.",
        )


class CompletionPaymentDialog(QDialog):
    """Collect the payment state at the moment a job is finalized."""

    def __init__(
        self,
        context: ApplicationContext,
        job_id: int,
        parent=None,
        agreed_price: float | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo = context.repository
        self.job_id = job_id
        summary = self.repo.job_payment_summary(job_id)
        total = float(summary["total"] if agreed_price is None else agreed_price)
        paid = float(summary["paid"])
        self.balance = max(total - paid, 0.0)
        self.setWindowTitle("Finalizar trabajo")
        self.setMinimumWidth(500)

        panel = Panel(
            "Cobro al finalizar",
            "Indica si el cliente pagó el saldo completo, una parte o si todavía no realizó un pago. Un cobro en el extranjero queda registrado en Caja, pero no aumenta el efectivo local.",
        )
        totals = QLabel(
            f"Precio acordado: ${total:,.2f}  ·  "
            f"Cobrado antes: ${paid:,.2f}  ·  Saldo: ${self.balance:,.2f}"
        )
        totals.setObjectName("MetricSubtitle")
        totals.setWordWrap(True)
        panel.body.addWidget(totals)

        self.mode = QComboBox()
        self.mode.addItems([
            "Pago completo",
            "Pago parcial",
            "Pago completo en el extranjero",
            "Pago parcial en el extranjero",
            "Sin pago en este momento",
        ])
        self.amount = _money_spin(self.balance, max(self.balance, 1_000_000.0))
        self.amount.setRange(0, max(self.balance, 0.0))
        self.tip = _money_spin(0, 1_000_000.0)
        self.date = _date_edit()
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Observación opcional del cobro")
        self.total_received = QLabel()
        self.total_received.setObjectName("MetricSubtitle")
        form = QFormLayout()
        form.setVerticalSpacing(11)
        form.addRow("Situación del pago", self.mode)
        form.addRow("Monto recibido", self.amount)
        form.addRow("Propina", self.tip)
        form.addRow("Fecha del cobro", self.date)
        form.addRow("Notas", self.notes)
        panel.body.addLayout(form)
        panel.body.addWidget(self.total_received)
        panel.body.addWidget(
            InfoBanner(
                "El trabajo quedará Finalizado aunque selecciones “Sin pago”. El saldo seguirá visible en Cobros. Un pago en el extranjero aparece en Caja como No efectivo y no modifica Dinero en efectivo.",
                "info",
            )
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Confirmar finalización")
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        layout.addWidget(panel)
        layout.addWidget(buttons)
        self.mode.currentTextChanged.connect(self.update_amount_state)
        self.amount.valueChanged.connect(self.update_total_received)
        self.tip.valueChanged.connect(self.update_total_received)
        self.update_amount_state()

    def update_amount_state(self, *_args) -> None:
        mode = self.mode.currentText()
        if mode in {"Pago completo", "Pago completo en el extranjero"}:
            self.amount.setValue(self.balance)
            self.amount.setEnabled(False)
        elif mode == "Sin pago en este momento":
            self.amount.setValue(0)
            self.amount.setEnabled(False)
            self.tip.setValue(0)
            self.tip.setEnabled(False)
        else:
            self.amount.setEnabled(True)
            self.tip.setEnabled(True)
            if self.balance > 0 and not (0 < self.amount.value() < self.balance):
                self.amount.setValue(min(self.balance, max(self.balance / 2, 0.01)))
        if mode in {"Pago completo", "Pago parcial", "Pago completo en el extranjero", "Pago parcial en el extranjero"}:
            self.tip.setEnabled(True)
        self.update_total_received()

    def update_total_received(self, *_args) -> None:
        self.total_received.setText(
            f"Total recibido incluyendo propina: ${self.amount.value() + self.tip.value():,.2f}"
        )

    def validate_and_accept(self) -> None:
        if "Pago parcial" in self.mode.currentText():
            if self.amount.value() <= 0:
                QMessageBox.warning(self, "Monto inválido", "Escribe el monto recibido.")
                return
            if self.amount.value() >= self.balance and self.balance > 0:
                QMessageBox.warning(
                    self,
                    "Monto inválido",
                    "Para un pago parcial el monto debe ser menor que el saldo. Selecciona Pago completo si corresponde.",
                )
                return
        if self.mode.currentText() == "Sin pago en este momento" and self.tip.value() > 0.005:
            QMessageBox.warning(self, "Propina sin pago", "Selecciona un tipo de pago para registrar la propina.")
            return
        self.accept()

    def payment_data(self) -> tuple[str, str, float, str, float] | None:
        amount = float(self.amount.value())
        tip = float(self.tip.value())
        if amount <= 0 and tip <= 0:
            return None
        mode = self.mode.currentText()
        foreign = "extranjero" in mode.casefold()
        if "Pago completo" in mode:
            payment_type = "Pago final en el extranjero" if foreign else "Pago final"
        else:
            payment_type = "Pago parcial en el extranjero" if foreign else "Pago parcial"
        return (
            self.date.date().toString("yyyy-MM-dd"),
            payment_type,
            amount,
            self.notes.text().strip(),
            tip,
        )


class JobDetailDialog(QDialog):
    def __init__(
        self,
        context: ApplicationContext,
        job_id: int,
        parent=None,
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.repo = context.repository
        self.services = context.services
        self.job_id = job_id
        self.on_saved = on_saved
        self.job = self.repo.get_job(job_id)
        if not self.job:
            raise ValueError("Trabajo no encontrado")
        self.measurement = (
            self.repo.get_measurement(int(self.job["measurement_id"]))
            if self.job["measurement_id"]
            else None
        )
        self._loading_measurement_lines = False
        self._updating_measurement = False
        self._measurement_price_overridden = False
        self._measurement_changed = False
        self.setWindowTitle(f"Trabajo de {self.job['client_name']}")
        self.resize(1260, 860)
        self.setMinimumSize(1040, 720)

        self.repo.ensure_job_material_plan(
            self.job_id,
            self.repo.setting_float("paint_coverage_m2", 25.0),
            self.repo.setting_float("mesh_roll_coverage_m2", 100.0),
        )
        # Repair jobs that were already marked En Progreso by an older version
        # but never removed their materials from stock.  Keep the dialog usable
        # if stock is insufficient and surface the reason inside Materiales.
        self.material_sync_error = ""
        self._last_material_messages: list[str] = []
        if self.job["status"] == "En Progreso":
            try:
                self.repo.ensure_in_progress_materials(self.job_id)
                self.job = self.repo.get_job(job_id)
            except ValueError as exc:
                self.material_sync_error = str(exc)

        header = Panel()
        header_row = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setFixedSize(48, 48)
        icon_label.setPixmap(icon("jobs", "#2563eb", 28).pixmap(28, 28))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background:#eff6ff; border-radius:12px;")
        header_row.addWidget(icon_label)
        title_col = QVBoxLayout()
        title = QLabel(self.job["client_name"])
        title.setObjectName("PageTitle")
        address = QLabel(self.job["client_address"] or "Sin dirección registrada")
        address.setObjectName("Muted")
        title_col.addWidget(title)
        title_col.addWidget(address)
        header_row.addLayout(title_col)
        header_row.addStretch()
        status = QLabel(self.job["status"])
        status.setStyleSheet(
            "background:#eef6ff; color:#1d4ed8; border-radius:9px; padding:7px 12px; font-weight:700;"
        )
        header_row.addWidget(status)
        header.body.addLayout(header_row)

        metrics = QGridLayout()
        self.new_metric = MetricCard("Desde cero", "measure", "blue", "Cuenta para rendimiento")
        self.maint_metric = MetricCard("Mantenimiento", "refresh", "amber", "No cuenta para rendimiento")
        self.price_metric = MetricCard("Precio acordado", "money", "green")
        metrics.addWidget(self.new_metric, 0, 0)
        metrics.addWidget(self.maint_metric, 0, 1)
        metrics.addWidget(self.price_metric, 0, 2)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_summary_tab(), icon("jobs", "#52647a", 17), "Resumen")
        self.tabs.addTab(self.build_measurement_tab(), icon("measure", "#52647a", 17), "Medidas")
        self.tabs.addTab(self.build_payroll_tab(), icon("brigades", "#52647a", 17), "Nómina")
        self.tabs.addTab(self.build_materials_tab(), icon("materials", "#52647a", 17), "Materiales")
        self.tabs.addTab(self.build_payments_tab(), icon("income", "#52647a", 17), "Cobros")
        self.crew.currentIndexChanged.connect(self.on_crew_changed)
        self.update_metrics()
        self.recalculate_measurement(update_materials=False, update_price=False)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Save).setText("Guardar cambios")
        buttons.button(QDialogButtonBox.Save).setIcon(icon("save", "#245caa", 17))
        buttons.accepted.connect(self.save_all)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(header)
        layout.addLayout(metrics)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)

    def build_summary_tab(self) -> QWidget:
        page = QWidget()
        root = QGridLayout(page)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        data_panel = Panel(
            "Datos y planificación",
            "Aquí puedes corregir teléfono, dirección, brigada, fechas y precio. Los metros se calculan en la pestaña Medidas.",
        )
        self.phone = QLineEdit(self.job["client_phone"] or "")
        self.phone.setPlaceholderText("Teléfono o teléfonos")
        self.address = QTextEdit(self.job["client_address"] or "")
        self.address.setMaximumHeight(76)
        self.address.setPlaceholderText("Dirección del techo")
        self.new_area = FlexibleDoubleSpinBox()
        self.new_area.setRange(0, 1_000_000)
        self.new_area.setDecimals(0)
        self.new_area.setSuffix(" m²")
        self.new_area.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.new_area.setReadOnly(True)
        self.new_area.setToolTip("Se calcula desde el desglose de la pestaña Medidas.")
        self.new_area.setValue(float(self.job["new_area"]))
        self.maint_area = FlexibleDoubleSpinBox()
        self.maint_area.setRange(0, 1_000_000)
        self.maint_area.setDecimals(0)
        self.maint_area.setSuffix(" m²")
        self.maint_area.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.maint_area.setReadOnly(True)
        self.maint_area.setToolTip("Se calcula desde el desglose de la pestaña Medidas.")
        self.maint_area.setValue(float(self.job["maintenance_area"]))
        self.status = QComboBox()
        self.status.addItems(["Medido", "Confirmado", "En Progreso", "Finalizado"])
        self.status.setCurrentText(self.job["status"])
        if self.job["status"] == "Finalizado":
            self.status.setEnabled(False)
            self.status.setToolTip("Un trabajo finalizado conserva su estado para proteger el historial financiero.")
        self.crew = QComboBox()
        self.crew.addItem("Sin asignar", None)
        for row in self.repo.active_crews():
            self.crew.addItem(row["name"], row["id"])
        idx = self.crew.findData(self.job["crew_id"])
        self.crew.setCurrentIndex(max(idx, 0))
        self.measurement_date = _date_edit(self.job["measurement_date"])
        self.start = _date_edit(self.job["start_date"])
        self.start.setToolTip(
            "Puedes corregir la fecha de inicio mientras el trabajo está confirmado o en progreso."
        )
        self.completion_label = QLabel(
            format_date(self.job["completion_date"])
            if self.job["completion_date"]
            else "Se registrará automáticamente al finalizar"
        )
        self.completion_label.setObjectName("Muted")
        self.completion_label.setWordWrap(True)
        self.agreed_price = _money_spin(float(self.job["agreed_price"]))
        self.new_area.valueChanged.connect(self.update_metrics)
        self.maint_area.valueChanged.connect(self.update_metrics)
        self.agreed_price.valueChanged.connect(self.update_metrics)
        self.agreed_price.editingFinished.connect(self.mark_measurement_price_manual)
        self.status.currentTextChanged.connect(self.update_date_controls)
        self.update_date_controls()

        form = QFormLayout()
        form.setVerticalSpacing(11)
        form.addRow("Teléfono(s)", self.phone)
        form.addRow("Dirección", self.address)
        form.addRow("Metros desde cero (calculados)", self.new_area)
        form.addRow("Metros de mantenimiento (calculados)", self.maint_area)
        form.addRow("Estado", self.status)
        form.addRow("Brigada responsable", self.crew)
        form.addRow("Fecha de medición", self.measurement_date)
        form.addRow("Fecha de inicio", self.start)
        form.addRow("Fecha de finalización", self.completion_label)
        form.addRow("Precio acordado", self.agreed_price)
        data_panel.body.addLayout(form)
        self.reprogram_button = button("Reprogramar trabajo y devolver materiales", "refresh")
        self.reprogram_button.setToolTip(
            "Cambia el trabajo a Confirmado, permite elegir una nueva fecha y devuelve al almacén los materiales retirados al guardar."
        )
        self.reprogram_button.clicked.connect(self.prepare_reschedule)
        self.reprogram_button.setVisible(self.job["status"] == "En Progreso")
        data_panel.body.addWidget(self.reprogram_button)

        notes_panel = Panel("Notas y trabajos adicionales")
        self.notes = QTextEdit(self.job["notes"] or "")
        self.notes.setPlaceholderText(
            "Registra albañilería, sustituciones, condiciones de la superficie y otros detalles."
        )
        notes_panel.body.addWidget(self.notes)
        notes_panel.body.addWidget(
            InfoBanner(
                "Los materiales se retiran del almacén cuando el trabajo pasa a En Progreso. Si se reprograma, se devuelven automáticamente. Al finalizar se registra la fecha, el cobro y el mantenimiento a 3 años.",
                "info",
            )
        )
        root.addWidget(data_panel, 0, 0)
        root.addWidget(notes_panel, 0, 1)
        root.setColumnStretch(0, 1)
        root.setColumnStretch(1, 2)
        return page

    def build_measurement_tab(self) -> QWidget:
        """Show and edit the detailed roof measurements stored for this job."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        if self.measurement:
            message = (
                "Este desglose queda guardado dentro de la medición de este trabajo. "
                "Edita la expresión o el resultado; los metros, el precio calculado, "
                "la nómina y la sugerencia de materiales se actualizarán automáticamente."
            )
        else:
            message = (
                "Este trabajo no tenía una medición asociada. Captura o corrige el "
                "desglose; al guardar se creará la medición para conservarlo."
            )
        layout.addWidget(InfoBanner(message, "info" if self.measurement else "warning"))

        toolbar = QHBoxLayout()
        add = button("Agregar medida", "plus")
        remove = button("Quitar seleccionada", "delete", "danger")
        quote = button("Vista previa para WhatsApp", "copy")
        use_calculated = button("Usar precio calculado", "refresh")
        add.clicked.connect(self.add_measurement_line)
        remove.clicked.connect(self.remove_measurement_line)
        quote.clicked.connect(self.show_measurement_quote)
        use_calculated.clicked.connect(self.use_calculated_measurement_price)
        toolbar.addWidget(add)
        toolbar.addWidget(remove)
        toolbar.addStretch()
        toolbar.addWidget(use_calculated)
        toolbar.addWidget(quote)
        layout.addLayout(toolbar)

        self.measurement_lines_table = QTableWidget()
        configure_table(
            self.measurement_lines_table,
            ["Texto original", "Expresión", "Resultado m²", "Sección", "Tipo", "Observación"],
            editable=True,
        )
        self.measurement_lines_table.setMinimumHeight(330)
        self.measurement_lines_table.itemChanged.connect(self._measurement_line_item_changed)
        layout.addWidget(self.measurement_lines_table, 1)

        summary = QHBoxLayout()
        self.measurement_new_total = QLabel("Desde cero: 0,00 m²")
        self.measurement_maint_total = QLabel("Mantenimiento: 0,00 m²")
        self.measurement_total = QLabel("Área total: 0,00 m²")
        self.measurement_calculated_price = QLabel("Precio calculado: $0.00")
        for label in (
            self.measurement_new_total,
            self.measurement_maint_total,
            self.measurement_total,
            self.measurement_calculated_price,
        ):
            label.setObjectName("MetricValue")
            summary.addWidget(label)
        layout.addLayout(summary)
        self.load_measurement_lines()
        return page

    def _measurement_line_rows_from_table(self, *, validate: bool = False) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in range(self.measurement_lines_table.rowCount()):
            original = self.measurement_lines_table.item(row, 0)
            expression = self.measurement_lines_table.item(row, 1)
            result_item = self.measurement_lines_table.item(row, 2)
            original_text = original.text().strip() if original else ""
            expression_text = expression.text().strip() if expression else ""
            try:
                result = float((result_item.text() if result_item else "0").replace(",", "."))
            except (TypeError, ValueError) as exc:
                if validate:
                    raise ValueError(f"Revisa el resultado de la medida en la fila {row + 1}.") from exc
                result = 0.0
            if validate:
                if not expression_text:
                    raise ValueError(f"La expresión de la fila {row + 1} no puede quedar vacía.")
                if result < 0:
                    raise ValueError(f"El resultado de la fila {row + 1} no puede ser negativo.")
                try:
                    self.services.measurements.calculate_expression_result(expression_text)
                except ValueError as exc:
                    raise ValueError(f"La expresión de la fila {row + 1} no es válida: {exc}") from exc
            rows.append(
                {
                    "original_text": original_text,
                    "expression": expression_text,
                    "result": result,
                    "section": self.measurement_lines_table.item(row, 3).text().strip()
                    if self.measurement_lines_table.item(row, 3)
                    else "Techo",
                    "work_type": self.measurement_lines_table.item(row, 4).text().strip()
                    if self.measurement_lines_table.item(row, 4)
                    else "Desde cero",
                    "observation": self.measurement_lines_table.item(row, 5).text().strip()
                    if self.measurement_lines_table.item(row, 5)
                    else "",
                }
            )
        return rows

    def _append_measurement_line(self, line: Mapping[str, Any]) -> None:
        row = self.measurement_lines_table.rowCount()
        self.measurement_lines_table.insertRow(row)
        values = [
            line.get("original_text", ""),
            line.get("expression", ""),
            f"{float(line.get('result', 0) or 0):.2f}",
            line.get("section", "Techo") or "Techo",
            line.get("work_type", "Desde cero") or "Desde cero",
            line.get("observation", "") or "",
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column == 2:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.measurement_lines_table.setItem(row, column, item)

    def load_measurement_lines(self) -> None:
        rows: list[Mapping[str, Any]] = [
            dict(row) for row in self.repo.measurement_lines(int(self.measurement["id"]))
        ] if self.measurement else []

        # A few very old records contain raw_text and totals but no line rows.
        # Reconstruct a useful editable breakdown on screen so the next save
        # upgrades that work to the current format.
        if not rows and self.measurement and self.measurement["raw_text"]:
            rows = [
                {
                    "original_text": line.original_text,
                    "expression": line.expression,
                    "result": line.result,
                    "section": line.section,
                    "work_type": line.work_type,
                    "observation": line.observation or line.error,
                }
                for line in self.services.measurements.parse(self.measurement["raw_text"])
            ]
        if not rows:
            if float(self.job["new_area"] or 0) > 0:
                rows.append(
                    {
                        "original_text": "Área histórica desde cero",
                        "expression": str(float(self.job["new_area"])),
                        "result": float(self.job["new_area"]),
                        "section": "Techo",
                        "work_type": "Desde cero",
                        "observation": "Reconstruida desde el total histórico",
                    }
                )
            if float(self.job["maintenance_area"] or 0) > 0:
                rows.append(
                    {
                        "original_text": "Área histórica de mantenimiento",
                        "expression": str(float(self.job["maintenance_area"])),
                        "result": float(self.job["maintenance_area"]),
                        "section": "Techo",
                        "work_type": "Mantenimiento",
                        "observation": "Reconstruida desde el total histórico",
                    }
                )

        self._loading_measurement_lines = True
        self.measurement_lines_table.setRowCount(0)
        for line in rows:
            self._append_measurement_line(line)
        self._loading_measurement_lines = False

    def _measurement_line_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading_measurement_lines or self._updating_measurement:
            return
        if item.column() == 1:
            try:
                result = self.services.measurements.calculate_expression_result(item.text())
            except ValueError:
                item.setBackground(QColor("#fef2f2"))
                item.setForeground(QColor("#b91c1c"))
            else:
                result_item = self.measurement_lines_table.item(item.row(), 2)
                self._updating_measurement = True
                if result_item:
                    result_item.setText(f"{result:.2f}")
                item.setBackground(QColor("#ffffff"))
                item.setForeground(QColor("#111827"))
                self._updating_measurement = False
        self._measurement_changed = True
        affects_totals = item.column() in (1, 2, 4)
        self.recalculate_measurement(
            update_materials=affects_totals,
            update_price=affects_totals,
        )

    def recalculate_measurement(
        self,
        *,
        update_materials: bool = True,
        update_price: bool = True,
    ) -> None:
        if not hasattr(self, "measurement_lines_table"):
            return
        rows = self._measurement_line_rows_from_table()
        totals = self.services.measurements.totals_from_rows(rows)
        self.measurement_new_total.setText(
            f"Desde cero: {totals.new_area:.2f} m²".replace(".", ",")
        )
        self.measurement_maint_total.setText(
            f"Mantenimiento: {totals.maintenance_area:.2f} m²".replace(".", ",")
        )
        self.measurement_total.setText(
            f"Área total: {totals.total_area:.2f} m²".replace(".", ",")
        )

        self._updating_measurement = True
        final_totals = MeasurementTotals(
            round_area(totals.new_area),
            round_area(totals.maintenance_area),
            round_area(totals.new_area) + round_area(totals.maintenance_area),
        )
        self.new_area.setValue(final_totals.new_area)
        self.maint_area.setValue(final_totals.maintenance_area)
        self._updating_measurement = False

        measurement = self.measurement
        price_new = float(measurement["price_new"]) if measurement else self.repo.setting_float("price_new", 10.0)
        price_maintenance = (
            float(measurement["price_maintenance"])
            if measurement
            else self.repo.setting_float("price_maintenance", 6.0)
        )
        masonry = float(measurement["masonry_extra"]) if measurement else 0.0
        membrane = float(measurement["membrane_extra"]) if measurement else 0.0
        adjustment = float(measurement["manual_adjustment"]) if measurement else 0.0
        calculated_price = self.services.measurements.calculate_price(
            final_totals, price_new, price_maintenance, masonry, membrane, adjustment
        )
        self.measurement_calculated_price.setText(f"Precio calculado: ${calculated_price:,.2f}")
        if update_price and not self._measurement_price_overridden:
            self._updating_measurement = True
            self.agreed_price.blockSignals(True)
            self.agreed_price.setValue(calculated_price)
            self.agreed_price.blockSignals(False)
            self._updating_measurement = False

        self.update_metrics()
        if hasattr(self, "payroll_table") and self.payroll_table.rowCount():
            self.recalculate_payroll()
        if update_materials and hasattr(self, "plan_table"):
            self.load_suggested_materials_for_measurement(final_totals)

    def load_suggested_materials_for_measurement(self, totals: MeasurementTotals | None = None) -> None:
        totals = totals or self.services.measurements.totals_from_rows(
            self._measurement_line_rows_from_table()
        )
        rows = self.repo.suggest_material_plan(
            totals.new_area,
            totals.maintenance_area,
            self.repo.setting_float("paint_coverage_m2", 25.0),
            self.repo.setting_float("mesh_roll_coverage_m2", 100.0),
        )
        self._loading_plan = True
        self.plan_table.setRowCount(0)
        self._loading_plan = False
        for row in rows:
            self._append_material_plan_row(
                int(row["material_id"]), float(row["quantity"]), 0, str(row["notes"])
            )

    def add_measurement_line(self) -> None:
        self._loading_measurement_lines = True
        self._append_measurement_line(
            {
                "original_text": "Nueva medida",
                "expression": "",
                "result": 0,
                "section": "Techo",
                "work_type": "Desde cero",
                "observation": "",
            }
        )
        self._loading_measurement_lines = False
        row = self.measurement_lines_table.rowCount() - 1
        self.measurement_lines_table.setCurrentCell(row, 1)
        self.measurement_lines_table.editItem(self.measurement_lines_table.item(row, 1))

    def remove_measurement_line(self) -> None:
        row = self.measurement_lines_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selecciona una medida", "Selecciona la fila que deseas quitar.")
            return
        self.measurement_lines_table.removeRow(row)
        self._measurement_changed = True
        self.recalculate_measurement()

    def mark_measurement_price_manual(self) -> None:
        if not self._updating_measurement:
            self._measurement_price_overridden = True

    def use_calculated_measurement_price(self) -> None:
        rows = self._measurement_line_rows_from_table()
        totals = self.services.measurements.totals_from_rows(rows)
        measurement = self.measurement
        calculated_price = self.services.measurements.calculate_price(
            MeasurementTotals(
                round_area(totals.new_area),
                round_area(totals.maintenance_area),
                round_area(totals.new_area) + round_area(totals.maintenance_area),
            ),
            float(measurement["price_new"]) if measurement else self.repo.setting_float("price_new", 10.0),
            float(measurement["price_maintenance"]) if measurement else self.repo.setting_float("price_maintenance", 6.0),
            float(measurement["masonry_extra"]) if measurement else 0.0,
            float(measurement["membrane_extra"]) if measurement else 0.0,
            float(measurement["manual_adjustment"]) if measurement else 0.0,
        )
        self._measurement_price_overridden = False
        self.agreed_price.blockSignals(True)
        self.agreed_price.setValue(calculated_price)
        self.agreed_price.blockSignals(False)
        self.update_metrics()

    def show_measurement_quote(self) -> None:
        rows = self._measurement_line_rows_from_table()
        totals = self.services.measurements.totals_from_rows(rows)
        if totals.total_area <= 0:
            QMessageBox.warning(self, "Sin medidas", "Primero captura al menos una medida válida.")
            return
        text = self.services.measurements.build_whatsapp_quote(
            rows, round_area(totals.total_area), self.agreed_price.value()
        )
        QuotePreviewDialog(text, self).exec()

    def update_date_controls(self, *_args) -> None:
        status = self.status.currentText()
        # La fecha de inicio puede corregirse mientras el trabajo está
        # confirmado o en progreso. Cambiarla en progreso solo corrige el dato
        # histórico; no vuelve a retirar materiales del almacén.
        editable = status in {"Confirmado", "En Progreso"}
        self.start.setEnabled(editable)
        if editable and not self.job["start_date"]:
            self.start.setDate(QDate.currentDate())
        if status == "Medido":
            self.start.setEnabled(False)
        if status == "Finalizado" and not self.job["completion_date"]:
            self.completion_label.setText("Se registrará con la fecha de hoy al guardar")

    def prepare_reschedule(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reprogramar trabajo",
            "El trabajo volverá a Confirmado. Al guardar, todos los materiales "
            "retirados para este trabajo se devolverán al almacén.\n\n"
            "Selecciona después una nueva fecha de inicio posterior a hoy.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        self.status.setCurrentText("Confirmado")
        self.start.setEnabled(True)
        self.start.setDate(QDate.currentDate().addDays(1))
        self.start.setFocus()

    def prepare_finalization(self) -> None:
        """Open the dialog ready to finish a job from the Dashboard."""
        if self.status.isEnabled():
            self.status.setCurrentText("Finalizado")
        self.tabs.setCurrentIndex(0)

    def update_metrics(self, *_args) -> None:
        if not hasattr(self, "new_area"):
            return
        self.new_metric.set_value(f"{self.new_area.value():,.0f} m²")
        self.maint_metric.set_value(f"{self.maint_area.value():,.0f} m²")
        self.price_metric.set_value(f"${self.agreed_price.value():,.2f}")

    def build_payroll_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(
            InfoBanner(
                "Al asignar una brigada se cargan sus integrantes habituales. Puedes sustituir trabajadores, cambiar su rol y ajustar el pago.",
                "info",
            )
        )
        bar = QHBoxLayout()
        generate = button("Restablecer según brigada", "refresh")
        generate.clicked.connect(self.generate_default_payroll)
        add = button("Agregar trabajador", "plus")
        add.clicked.connect(self.add_worker_row)
        remove = button("Quitar seleccionado", "delete", "danger")
        remove.clicked.connect(self.remove_worker_row)
        recalc = button("Recalcular", "refresh", "primary")
        recalc.clicked.connect(self.recalculate_payroll)
        bar.addWidget(generate)
        bar.addWidget(add)
        bar.addWidget(remove)
        bar.addStretch()
        bar.addWidget(recalc)
        layout.addLayout(bar)

        self.payroll_table = QTableWidget()
        configure_table(
            self.payroll_table,
            [
                "Trabajador", "Rol", "Tarifa cero", "Tarifa mant.", "Base",
                "Redondeado", "Ajuste", "Motivo", "Pago final",
            ],
            editable=True,
        )
        self.payroll_table.setMinimumHeight(330)
        layout.addWidget(self.payroll_table, 1)
        footer = QHBoxLayout()
        footer.addWidget(QLabel("Los pagos se redondean al múltiplo de 5 más cercano."))
        footer.addStretch()
        self.payroll_total = QLabel("Total nómina: $0.00")
        self.payroll_total.setObjectName("MetricValue")
        footer.addWidget(self.payroll_total)
        layout.addLayout(footer)
        self.load_payroll()
        return page

    def _append_payroll_row(self, line: PayrollLine) -> None:
        row = self.payroll_table.rowCount()
        self.payroll_table.insertRow(row)
        values = [
            line.name, line.role, f"{line.rate_new:.2f}", f"{line.rate_maintenance:.2f}",
            f"{line.base_pay:.2f}", f"{line.rounded_pay:.2f}",
            f"{line.manual_adjustment:.2f}", line.adjustment_reason, f"{line.final_pay:.2f}",
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if col in (0, 4, 5, 8):
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.payroll_table.setItem(row, col, item)
        self.payroll_table.item(row, 0).setData(Qt.UserRole, line.worker_id)

    def load_payroll(self) -> None:
        self.payroll_table.setRowCount(0)
        rows = self.repo.job_payroll(self.job_id)
        for row in rows:
            self._append_payroll_row(
                PayrollLine(
                    worker_id=int(row["worker_id"]), name=row["name"], role=row["role"],
                    rate_new=float(row["rate_new"]), rate_maintenance=float(row["rate_maintenance"]),
                    base_pay=float(row["base_pay"]), rounded_pay=float(row["rounded_pay"]),
                    manual_adjustment=float(row["manual_adjustment"]),
                    adjustment_reason=row["adjustment_reason"], final_pay=float(row["final_pay"]),
                    counts_for_worker_meters=bool(row["counts_for_worker_meters"]),
                )
            )
        if not rows and self.crew.currentData() is not None:
            self.generate_default_payroll()
        else:
            self.update_payroll_total()

    def on_crew_changed(self, *_args) -> None:
        if hasattr(self, "payroll_table") and self.payroll_table.rowCount() == 0 and self.crew.currentData() is not None:
            self.generate_default_payroll()

    def generate_default_payroll(self) -> None:
        if self.crew.currentData() is None:
            self.payroll_table.setRowCount(0)
            self.update_payroll_total()
            return
        self.payroll_table.setRowCount(0)
        for line in self.services.payroll.default_lines(self.crew.currentText()):
            self._append_payroll_row(line)
        self.recalculate_payroll()

    def add_worker_row(self) -> None:
        existing = {
            self.payroll_table.item(row, 0).data(Qt.UserRole)
            for row in range(self.payroll_table.rowCount())
        }
        options = [row for row in self.repo.workers_basic(True) if row["id"] not in existing]
        if not options:
            QMessageBox.information(self, "Sin trabajadores", "Todos los trabajadores activos ya están agregados.")
            return
        selected, ok = QInputDialog.getItem(
            self, "Agregar trabajador", "Trabajador", [row["name"] for row in options], 0, False
        )
        if not ok:
            return
        worker = next(row for row in options if row["name"] == selected)
        self._append_payroll_row(
            PayrollLine(
                worker_id=int(worker["id"]), name=worker["name"], role=worker["base_role"],
                rate_new=self.repo.setting_float("rate_helper_new", 0.5),
                rate_maintenance=self.repo.setting_float("rate_maintenance", 0.3),
                counts_for_worker_meters=not bool(worker["is_partner"]),
            )
        )
        self.recalculate_payroll()

    def remove_worker_row(self) -> None:
        row = self.payroll_table.currentRow()
        if row >= 0:
            self.payroll_table.removeRow(row)
            self.update_payroll_total()

    def _payroll_lines_from_table(self) -> list[PayrollLine]:
        lines: list[PayrollLine] = []
        for row in range(self.payroll_table.rowCount()):
            name = self.payroll_table.item(row, 0).text()
            role = self.payroll_table.item(row, 1).text().strip()
            try:
                parse = lambda col: float((self.payroll_table.item(row, col).text() or "0").replace(",", "."))
                line = PayrollLine(
                    worker_id=int(self.payroll_table.item(row, 0).data(Qt.UserRole)),
                    name=name, role=role, rate_new=parse(2), rate_maintenance=parse(3),
                    base_pay=parse(4), rounded_pay=parse(5), manual_adjustment=parse(6),
                    adjustment_reason=self.payroll_table.item(row, 7).text().strip(),
                    final_pay=parse(8),
                    counts_for_worker_meters=(name != "Socio" and role.lower() != "administrador"),
                )
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValueError(f"Revisa las tarifas y el ajuste en la fila {row + 1}.") from exc
            lines.append(line)
        return lines

    def recalculate_payroll(self) -> bool:
        try:
            lines = self._payroll_lines_from_table()
        except ValueError as exc:
            QMessageBox.warning(self, "Dato inválido", str(exc))
            return False
        calculated = self.services.payroll.calculate_all(
            lines, self.new_area.value(), self.maint_area.value()
        )
        for row, line in enumerate(calculated):
            self.payroll_table.item(row, 4).setText(f"{line.base_pay:.2f}")
            self.payroll_table.item(row, 5).setText(f"{line.rounded_pay:.2f}")
            self.payroll_table.item(row, 8).setText(f"{line.final_pay:.2f}")
        self.update_payroll_total()
        return True

    def update_payroll_total(self) -> None:
        total = 0.0
        for row in range(self.payroll_table.rowCount()):
            try:
                total += float(self.payroll_table.item(row, 8).text().replace(",", "."))
            except (ValueError, AttributeError):
                pass
        self.payroll_total.setText(f"Total nómina: ${total:,.2f}")

    def save_payroll(self) -> bool:
        if self.payroll_table.rowCount() == 0 and self.crew.currentData() is not None:
            self.generate_default_payroll()
        if not self.recalculate_payroll():
            return False
        try:
            lines = self._payroll_lines_from_table()
        except ValueError as exc:
            QMessageBox.warning(self, "Dato inválido", str(exc))
            return False
        self.services.payroll.save(self.job_id, lines)
        return True

    def build_materials_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        running = self.job["status"] in {"En Progreso", "Finalizado"}
        if running:
            explanation = (
                "Este trabajo ya retiró materiales del almacén. La columna Cantidad usada representa "
                "el consumo real: si reduces una cantidad, el sobrante vuelve al stock; si la aumentas, "
                "solo se descuenta la diferencia. Los litros se recalculan automáticamente."
            )
        else:
            explanation = (
                "Estas son las cantidades previstas antes de comenzar. Puedes cambiarlas libremente. "
                "Cuando el trabajo pase a En Progreso se retirarán del almacén exactamente estas cantidades."
            )
        layout.addWidget(InfoBanner(explanation, "info"))
        if self.material_sync_error:
            layout.addWidget(
                InfoBanner(
                    "El programa detectó que este trabajo figura En Progreso pero no pudo regularizar "
                    f"el inventario: {self.material_sync_error}",
                    "warning",
                )
            )

        plan_bar = QHBoxLayout()
        self.material_plan_title = QLabel(
            "Consumo real del trabajo" if running else "Materiales previstos"
        )
        self.material_plan_title.setObjectName("SectionTitle")
        add_plan = button("Agregar material", "plus")
        add_plan.clicked.connect(self.add_material_plan_row)
        remove_plan = button("Quitar seleccionado", "delete", "danger")
        remove_plan.clicked.connect(self.remove_material_plan_row)
        self.save_plan_button = button(
            "Guardar consumo y ajustar stock" if running else "Guardar cantidades previstas",
            "save",
            "primary",
        )
        self.save_plan_button.clicked.connect(self.save_material_plan)
        reset_plan = button("Restablecer sugerencia", "refresh")
        reset_plan.clicked.connect(self.reset_material_plan)
        plan_bar.addWidget(self.material_plan_title)
        plan_bar.addWidget(add_plan)
        plan_bar.addWidget(remove_plan)
        plan_bar.addStretch()
        plan_bar.addWidget(reset_plan)
        plan_bar.addWidget(self.save_plan_button)
        layout.addLayout(plan_bar)

        self.plan_table = QTableWidget()
        quantity_header = "Cantidad usada" if running else "Cantidad prevista"
        configure_table(
            self.plan_table,
            ["Material", quantity_header, "Litros", "Costo", "Stock en almacén", "Notas"],
            editable=True,
        )
        self.plan_table.setMinimumHeight(230)
        self.plan_table.itemChanged.connect(self._plan_item_changed)
        self._loading_plan = False
        layout.addWidget(self.plan_table)

        history_title = QLabel("Historial de movimientos del almacén")
        history_title.setObjectName("SectionTitle")
        layout.addWidget(history_title)
        layout.addWidget(
            InfoBanner(
                "Esta tabla es solo el historial de auditoría. 'Salida al trabajo' resta stock y "
                "'Devolución al almacén' lo repone. No se registran compras desde un trabajo; "
                "las compras se gestionan únicamente en la sección Materiales.",
                "info",
            )
        )
        self.material_table = QTableWidget()
        configure_table(
            self.material_table,
            ["Fecha", "Movimiento", "Material", "Marca", "Cantidad", "Litros", "Costo", "Notas"],
        )
        self.material_table.setMinimumHeight(190)
        layout.addWidget(self.material_table, 1)
        self.load_material_plan()
        self.load_materials()
        return page

    def _material_choices(self) -> list[object]:
        return list(self.repo.list_materials(True))

    def _append_material_plan_row(
        self, material_id: int | None = None, quantity: float = 0.0,
        liters: float = 0.0, notes: str = "",
    ) -> None:
        was_loading = self._loading_plan
        self._loading_plan = True
        try:
            row = self.plan_table.rowCount()
            self.plan_table.insertRow(row)
            combo = QComboBox()
            for material in self._material_choices():
                combo.addItem(
                    material["name"],
                    (
                        int(material["id"]), float(material["package_size"]),
                        float(material["average_unit_cost"]), float(material["stock_quantity"]),
                        str(material["unit"]), str(material["category"]),
                    ),
                )
            if material_id is not None:
                for index in range(combo.count()):
                    if int(combo.itemData(index)[0]) == int(material_id):
                        combo.setCurrentIndex(index)
                        break
            combo.currentIndexChanged.connect(lambda _index, widget=combo: self._material_combo_changed(widget))
            self.plan_table.setCellWidget(row, 0, combo)
            self.plan_table.setItem(row, 1, QTableWidgetItem(f"{float(quantity):.2f}"))
            liters_item = QTableWidgetItem(f"{float(liters):.2f}")
            liters_item.setFlags(liters_item.flags() & ~Qt.ItemIsEditable)
            self.plan_table.setItem(row, 2, liters_item)
            cost_item = QTableWidgetItem("$0.00")
            cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
            self.plan_table.setItem(row, 3, cost_item)
            stock_item = QTableWidgetItem("")
            stock_item.setFlags(stock_item.flags() & ~Qt.ItemIsEditable)
            self.plan_table.setItem(row, 4, stock_item)
            self.plan_table.setItem(row, 5, QTableWidgetItem(notes))
        finally:
            self._loading_plan = was_loading
        self._update_material_plan_row(row)

    def _row_for_combo(self, combo: QComboBox) -> int:
        for row in range(self.plan_table.rowCount()):
            if self.plan_table.cellWidget(row, 0) is combo:
                return row
        return -1

    def _material_combo_changed(self, combo: QComboBox) -> None:
        row = self._row_for_combo(combo)
        if row >= 0:
            self._update_material_plan_row(row)

    @staticmethod
    def _number_from_item(item: QTableWidgetItem | None) -> float:
        try:
            return float((item.text() if item else "0").replace(",", "."))
        except ValueError:
            return 0.0

    def _update_material_plan_row(self, row: int) -> None:
        if self._loading_plan or row < 0:
            return
        combo = self.plan_table.cellWidget(row, 0)
        if not isinstance(combo, QComboBox) or not combo.currentData():
            return
        _material_id, package_size, average_cost, stock, unit, category = combo.currentData()
        quantity = self._number_from_item(self.plan_table.item(row, 1))
        self._loading_plan = True
        liters = quantity * float(package_size) if str(category) == "Pintura" else 0.0
        self.plan_table.item(row, 2).setText(f"{liters:.2f}")
        self.plan_table.item(row, 3).setText(f"${quantity * float(average_cost):,.2f}")
        self.plan_table.item(row, 4).setText(f"{float(stock):.2f} {unit}(s)")
        self._loading_plan = False

    def _plan_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading_plan:
            return
        if item.column() == 1:
            self._update_material_plan_row(item.row())

    def load_material_plan(self) -> None:
        rows = self.repo.job_material_plan(self.job_id)
        self._loading_plan = True
        self.plan_table.setRowCount(0)
        self._loading_plan = False
        for row in rows:
            self._append_material_plan_row(
                int(row["material_id"]), float(row["quantity"]), float(row["liters"]), row["notes"] or ""
            )

    def add_material_plan_row(self) -> None:
        used = {
            int(self.plan_table.cellWidget(row, 0).currentData()[0])
            for row in range(self.plan_table.rowCount())
            if isinstance(self.plan_table.cellWidget(row, 0), QComboBox)
            and self.plan_table.cellWidget(row, 0).currentData()
        }
        available = [row for row in self._material_choices() if int(row["id"]) not in used]
        if not available:
            QMessageBox.information(self, "Sin más materiales", "Todos los tipos de material ya están incluidos.")
            return
        self._append_material_plan_row(int(available[0]["id"]), 0, 0, "Agregado manualmente")

    def remove_material_plan_row(self) -> None:
        row = self.plan_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selecciona un material", "Selecciona la fila que deseas quitar.")
            return
        self.plan_table.removeRow(row)

    def material_plan_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        used: set[int] = set()
        for r in range(self.plan_table.rowCount()):
            combo = self.plan_table.cellWidget(r, 0)
            if not isinstance(combo, QComboBox) or not combo.currentData():
                continue
            material_id = int(combo.currentData()[0])
            if material_id in used:
                raise ValueError("Un mismo tipo de material no puede aparecer dos veces.")
            used.add(material_id)
            try:
                quantity = float(self.plan_table.item(r, 1).text().replace(",", "."))
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"Revisa las cantidades previstas en la fila {r + 1}.") from exc
            package_size = float(combo.currentData()[1])
            category = str(combo.currentData()[5])
            liters = quantity * package_size if category == "Pintura" else 0.0
            rows.append({
                "material_id": material_id,
                "quantity": quantity,
                "liters": liters,
                "notes": self.plan_table.item(r, 5).text().strip(),
            })
        return rows

    def save_material_plan(self, *, notify: bool = True) -> bool:
        self._last_material_messages = []
        previous_plan = [
            {
                "material_id": int(row["material_id"]),
                "quantity": float(row["quantity"]),
                "notes": row["notes"] or "",
            }
            for row in self.repo.job_material_plan(self.job_id)
        ]
        should_sync_stock = (
            self.job["status"] in {"En Progreso", "Finalizado"}
            and not (
                self.job["status"] == "En Progreso"
                and self.status.currentText() in {"Confirmado", "Medido"}
            )
        )
        try:
            self.repo.save_job_material_plan(self.job_id, self.material_plan_rows())
            # Once stock has been checked out, the editable quantities are the
            # real consumption target. Reconcile the warehouse immediately so
            # the stock, liters and audit history always agree with the table.
            if should_sync_stock:
                movement_date = (
                    self.job["completion_date"]
                    or self.job["start_date"]
                    or QDate.currentDate().toString("yyyy-MM-dd")
                )
                self._last_material_messages = self.repo.reconcile_job_materials_to_plan(
                    self.job_id,
                    movement_date=str(movement_date),
                    note_prefix="Ajuste manual del consumo real",
                )
                self.material_sync_error = ""
                self.job = self.repo.get_job(self.job_id)
        except ValueError as exc:
            # The stock reconciliation validates before writing movements, so
            # restoring the previous plan leaves both plan and warehouse in the
            # exact state they had before the attempted edit.
            try:
                self.repo.save_job_material_plan(self.job_id, previous_plan)
            except Exception:
                pass
            self.load_material_plan()
            self.load_materials()
            QMessageBox.warning(self, "No se pudieron ajustar los materiales", str(exc))
            return False
        self.load_material_plan()
        self.load_materials()
        if notify:
            if should_sync_stock:
                detail = "El consumo real y el stock del almacén quedaron sincronizados."
                if self._last_material_messages:
                    detail += "\n\n" + "\n".join(f"• {msg}" for msg in self._last_material_messages)
                QMessageBox.information(self, "Materiales actualizados", detail)
            else:
                QMessageBox.information(
                    self,
                    "Materiales previstos",
                    "Las cantidades previstas quedaron guardadas. Se descontarán cuando el trabajo comience.",
                )
        return True

    def reset_material_plan(self) -> None:
        running = self.job["status"] in {"En Progreso", "Finalizado"}
        if running:
            answer = QMessageBox.question(
                self,
                "Restablecer materiales",
                "El trabajo ya tiene materiales retirados. Restablecer la sugerencia también ajustará "
                "el stock del almacén para que coincida con las nuevas cantidades. ¿Continuar?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        previous_plan = [
            {
                "material_id": int(row["material_id"]),
                "quantity": float(row["quantity"]),
                "notes": row["notes"] or "",
            }
            for row in self.repo.job_material_plan(self.job_id)
        ]
        self.repo.reset_job_material_plan(
            self.job_id,
            self.repo.setting_float("paint_coverage_m2", 25.0),
            self.repo.setting_float("mesh_roll_coverage_m2", 100.0),
            new_area=self.new_area.value(),
            maintenance_area=self.maint_area.value(),
        )
        if running:
            try:
                self.repo.reconcile_job_materials_to_plan(
                    self.job_id,
                    movement_date=QDate.currentDate().toString("yyyy-MM-dd"),
                    note_prefix="Restablecimiento de materiales del trabajo",
                )
            except ValueError as exc:
                self.repo.save_job_material_plan(self.job_id, previous_plan)
                QMessageBox.warning(self, "No se pudo ajustar el stock", str(exc))
        self.load_material_plan()
        self.load_materials()

    def load_materials(self) -> None:
        rows = self.repo.material_movements(self.job_id)
        self.material_table.setRowCount(len(rows))
        labels = {
            "Consumo": "Salida al trabajo",
            "Devolución": "Devolución al almacén",
            "Compra": "Compra",
        }
        for r, row in enumerate(rows):
            values = [
                format_date(row["movement_date"]), labels.get(row["movement_type"], row["movement_type"]),
                row["material"], row["brand"] or "—", f"{float(row['quantity']):.2f}",
                f"{float(row['liters']):.2f}", f"${float(row['total_cost']):,.2f}", row["notes"],
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.material_table.setItem(r, c, item)

    def open_material_movement(self, movement_type: str) -> None:
        dialog = MaterialMovementDialog(self.context, movement_type, self)
        if movement_type == "Consumo":
            idx = dialog.job.findData(self.job_id)
            dialog.job.setCurrentIndex(max(idx, 0))
        if dialog.exec():
            self.load_materials()

    def build_payments_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        add = button("Registrar cobro", "income", "primary")
        edit = button("Editar cobro", "edit")
        delete = button("Eliminar cobro", "delete", "danger")
        add.clicked.connect(self.add_payment)
        edit.clicked.connect(self.edit_payment)
        delete.clicked.connect(self.delete_payment)
        self.edit_payment_button = edit
        self.delete_payment_button = delete
        toolbar.addWidget(add)
        toolbar.addWidget(delete)
        toolbar.addWidget(edit)
        toolbar.addStretch()
        self.balance_label = QLabel()
        self.balance_label.setObjectName("MetricValue")
        toolbar.addWidget(self.balance_label)
        layout.addLayout(toolbar)
        layout.addWidget(
            InfoBanner(
                "Selecciona un cobro para editarlo o eliminarlo. Si lo eliminas, Caja, Dashboard e Ingresos se actualizarán y el saldo del trabajo volverá a quedar pendiente.",
                "info",
            )
        )
        self.payments_table = QTableWidget()
        configure_table(self.payments_table, ["Fecha", "Tipo", "Monto", "Propina", "Notas"])
        self.payments_table.itemSelectionChanged.connect(self.update_payment_actions)
        layout.addWidget(self.payments_table, 1)
        self.load_payments()
        return page

    def load_payments(self) -> None:
        rows = self.repo.payments(self.job_id)
        self.payments_table.setRowCount(len(rows))
        total = 0.0
        for r, row in enumerate(rows):
            total += max(float(row["amount"] or 0) - float(row["tip_amount"] or 0), 0.0)
            values = [
                format_date(row["payment_date"]), row["payment_type"],
                f"${float(row['amount']):,.2f}", f"${float(row['tip_amount'] or 0):,.2f}", row["notes"],
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 0:
                    item.setData(Qt.UserRole, int(row["id"]))
                self.payments_table.setItem(r, c, item)
        balance = self.agreed_price.value() - total
        self.balance_label.setText(f"Cobrado ${total:,.2f} · Saldo ${balance:,.2f}")
        self.update_payment_actions()

    def selected_payment_id(self) -> int | None:
        row = self.payments_table.currentRow()
        if row < 0 or not self.payments_table.item(row, 0):
            return None
        value = self.payments_table.item(row, 0).data(Qt.UserRole)
        return int(value) if value else None

    def update_payment_actions(self) -> None:
        selected = self.selected_payment_id() is not None
        self.edit_payment_button.setEnabled(selected)
        self.delete_payment_button.setEnabled(selected)

    def add_payment(self) -> None:
        if PaymentDialog(self.context, self.job_id, self).exec():
            self.load_payments()
            if self.on_saved:
                self.on_saved()

    def edit_payment(self) -> None:
        payment_id = self.selected_payment_id()
        if not payment_id:
            QMessageBox.information(self, "Selecciona un cobro", "Selecciona el cobro que deseas editar.")
            return
        if PaymentDialog(self.context, self.job_id, self, payment_id=payment_id).exec():
            self.load_payments()
            if self.on_saved:
                self.on_saved()

    def delete_payment(self) -> None:
        payment_id = self.selected_payment_id()
        if not payment_id:
            QMessageBox.information(self, "Selecciona un cobro", "Selecciona el cobro que deseas eliminar.")
            return
        payment = self.repo.payment(payment_id, self.job_id)
        if not payment:
            self.load_payments()
            return
        answer = QMessageBox.question(
            self,
            "Eliminar cobro",
            f"¿Eliminar el cobro de ${float(payment['amount']):,.2f}?\n\n"
            "También desaparecerá de Caja, Dashboard e Ingresos y el saldo del trabajo se recalculará.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repo.delete_payment(payment_id, self.job_id)
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo eliminar", str(exc))
            return
        self.load_payments()
        if self.on_saved:
            self.on_saved()

    def save_all(self) -> None:
        try:
            measurement_rows = self._measurement_line_rows_from_table(validate=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Medidas inválidas", str(exc))
            self.tabs.setCurrentIndex(1)
            return
        if not measurement_rows:
            QMessageBox.warning(self, "Medición vacía", "Agrega al menos una medida antes de guardar el trabajo.")
            self.tabs.setCurrentIndex(1)
            return
        finalizing = (
            self.status.currentText() == "Finalizado"
            and self.job["status"] != "Finalizado"
        )
        reprogramming = (
            self.job["status"] == "En Progreso"
            and self.status.currentText() in {"Confirmado", "Medido"}
        )
        if reprogramming:
            answer = QMessageBox.question(
                self,
                "Confirmar reprogramación",
                "Al guardar se devolverán al almacén todos los consumos de materiales "
                "registrados para este trabajo. ¿Deseas continuar?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
        payment_data: tuple[str, str, float, str, float] | None = None
        if finalizing:
            payment_summary = self.repo.job_payment_summary(
                self.job_id,
                agreed_price=self.agreed_price.value(),
            )
            # If the balance was already covered from the Cobros tab, there is
            # no second payment decision to make while finishing the job.
            if payment_summary["balance"] > 0.005:
                payment_dialog = CompletionPaymentDialog(
                    self.context,
                    self.job_id,
                    self,
                    agreed_price=self.agreed_price.value(),
                )
                if payment_dialog.exec() != QDialog.Accepted:
                    return
                payment_data = payment_dialog.payment_data()

        if not self.save_material_plan(notify=False):
            return
        if not self.save_payroll():
            return

        auto_deduct = False
        completing = self.status.currentText() == "Finalizado"
        if completing and not bool(self.job["materials_deducted"]):
            existing_consumption = self.repo.job_material_consumption_count(self.job_id)
            if existing_consumption == 0:
                plan = self.repo.job_material_plan(self.job_id)
                description = ", ".join(
                    f"{float(row['quantity']):g} {row['unit']}(s) de {row['material']}" for row in plan
                ) or "ningún material"
                answer = QMessageBox.question(
                    self,
                    "Descontar materiales",
                    "Este trabajo no tiene consumos reales registrados. Al completarlo se descontará del inventario:\n\n"
                    f"{description}\n\n¿Continuar?",
                    QMessageBox.Yes | QMessageBox.Cancel,
                    QMessageBox.Yes,
                )
                if answer != QMessageBox.Yes:
                    return
            auto_deduct = True

        try:
            material_messages = list(self._last_material_messages)
            material_messages.extend(self.services.jobs.save_job(
                job_id=self.job_id,
                current_job=self.job,
                status=self.status.currentText(),
                crew_id=self.crew.currentData(),
                measurement_date=self.measurement_date.date().toString("yyyy-MM-dd"),
                start_date=(
                    self.start.date().toString("yyyy-MM-dd")
                    if self.status.currentText() in {"Confirmado", "En Progreso", "Finalizado"}
                    else None
                ),
                completion_date=QDate.currentDate().toString("yyyy-MM-dd") if finalizing else None,
                agreed_price=self.agreed_price.value(),
                notes=self.notes.toPlainText().strip(),
                new_area=self.new_area.value(),
                maintenance_area=self.maint_area.value(),
                phone=self.phone.text().strip(),
                address=self.address.toPlainText().strip(),
                auto_deduct_materials=auto_deduct,
                measurement_rows=measurement_rows,
            ))
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo completar", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "No se pudieron guardar los cambios", str(exc))
            return

        if payment_data:
            payment_date, payment_type, amount, payment_notes, tip_amount = payment_data
            self.repo.add_payment(
                self.job_id,
                payment_date,
                payment_type,
                amount,
                payment_notes,
                tip_amount=tip_amount,
            )

        if self.on_saved:
            self.on_saved()
        detail = "Los cambios se guardaron correctamente."
        if material_messages:
            detail += "\n\nMovimientos de materiales:\n• " + "\n• ".join(material_messages)
        QMessageBox.information(self, "Trabajo actualizado", detail)
        self.accept()
