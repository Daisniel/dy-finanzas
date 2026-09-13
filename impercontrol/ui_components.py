from __future__ import annotations

from typing import Iterable, Sequence

from PySide6.QtCore import (
    QEvent,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QTimer,
    Qt,
    QLocale,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QAbstractItemView,
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .icons import icon


class FlexibleDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that accepts both decimal comma and decimal point.

    The display uses a decimal point for consistency, but users may type either
    ``3.5`` or ``3,5``.  Prefixes/suffixes continue to work normally.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setLocale(QLocale.c())

    @staticmethod
    def _normalize(text: str) -> str:
        return str(text).replace(",", ".")

    def validate(self, text: str, pos: int):  # noqa: N802 - Qt API
        return super().validate(self._normalize(text), pos)

    def valueFromText(self, text: str) -> float:  # noqa: N802 - Qt API
        return super().valueFromText(self._normalize(text))

    def fixup(self, text: str):  # noqa: N802 - Qt API
        return super().fixup(self._normalize(text))


class _GlobalSpinBoxWheelFilter(QObject):
    """Disable mouse-wheel value changes for every numeric spin box.

    If the field lives inside a scrollable page, the wheel movement is passed
    conceptually to that page instead.  Otherwise it is simply consumed.  This
    applies to existing and future numeric/date spin boxes and combo boxes.
    """

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, (QAbstractSpinBox, QComboBox)):
            return False

        parent = watched.parentWidget()
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()

        if isinstance(parent, QAbstractScrollArea):
            delta = event.pixelDelta().y() or event.angleDelta().y()
            scrollbar = parent.verticalScrollBar()
            if delta:
                if event.pixelDelta().y():
                    movement = int(delta)
                else:
                    movement = int((delta / 120) * max(scrollbar.singleStep() * 3, 30))
                scrollbar.setValue(scrollbar.value() - movement)
        event.accept()
        return True


def install_global_numeric_input_behavior(application) -> None:
    """Install application-wide safe mouse-wheel behavior for numeric fields."""
    if getattr(application, "_numeric_wheel_filter", None) is not None:
        return
    wheel_filter = _GlobalSpinBoxWheelFilter(application)
    application.installEventFilter(wheel_filter)
    application._numeric_wheel_filter = wheel_filter  # type: ignore[attr-defined]


class _SpinBoxWheelRedirectFilter(QObject):
    """Prevent accidental value changes while the user scrolls a form.

    Qt spin boxes consume wheel events even when the intention is to move the
    surrounding page.  This filter redirects the wheel movement to the nearest
    scroll area and leaves the numeric value untouched.
    """

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() != QEvent.Type.Wheel:
            return False

        parent = watched.parentWidget() if hasattr(watched, "parentWidget") else None
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()

        if isinstance(parent, QAbstractScrollArea):
            delta = event.pixelDelta().y() or event.angleDelta().y()
            scrollbar = parent.verticalScrollBar()
            if delta:
                # Three line steps per regular mouse-wheel notch feels close
                # to Qt's native page scrolling without changing the field.
                if event.pixelDelta().y():
                    movement = int(delta)
                else:
                    movement = int((delta / 120) * max(scrollbar.singleStep() * 3, 30))
                scrollbar.setValue(scrollbar.value() - movement)
        event.accept()
        return True


def disable_spinbox_wheel(widget: QAbstractSpinBox) -> QAbstractSpinBox:
    """Make a spin box keyboard/manual-entry only for mouse-wheel purposes."""
    wheel_filter = _SpinBoxWheelRedirectFilter(widget)
    widget.installEventFilter(wheel_filter)
    widget._wheel_redirect_filter = wheel_filter  # type: ignore[attr-defined]
    return widget


def set_role(widget: QWidget, role: str) -> QWidget:
    widget.setProperty("role", role)
    return widget


def button(text: str, icon_name: str | None = None, role: str = "secondary") -> QPushButton:
    widget = QPushButton(text)
    set_role(widget, role)
    if icon_name:
        widget.setIcon(icon(icon_name, "#ffffff" if role == "primary" else "#245caa", 18))
    widget.setCursor(Qt.PointingHandCursor)
    return widget


class Panel(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 20)
        self._layout.setSpacing(14)
        if title:
            header = QVBoxLayout()
            header.setSpacing(3)
            title_label = QLabel(title)
            title_label.setObjectName("PanelTitle")
            title_label.setWordWrap(True)
            title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            header.addWidget(title_label)
            if subtitle:
                subtitle_label = QLabel(subtitle)
                subtitle_label.setObjectName("PanelSubtitle")
                subtitle_label.setWordWrap(True)
                header.addWidget(subtitle_label)
            self._layout.addLayout(header)

    @property
    def body(self) -> QVBoxLayout:
        return self._layout


class MetricCard(QFrame):
    def __init__(
        self,
        title: str,
        icon_name: str,
        accent: str = "blue",
        subtitle: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setProperty("accent", accent)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)
        top = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("MetricTitle")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.title_label = label
        top.addWidget(label, 1)
        top.addStretch()
        glyph = QLabel()
        glyph.setObjectName("MetricIcon")
        glyph.setFixedSize(34, 34)
        color_map = {
            "blue": "#2563eb",
            "green": "#16a34a",
            "red": "#dc2626",
            "amber": "#d97706",
            "purple": "#7c3aed",
            "cyan": "#0891b2",
        }
        glyph.setPixmap(icon(icon_name, color_map.get(accent, "#2563eb"), 20).pixmap(20, 20))
        glyph.setAlignment(Qt.AlignCenter)
        top.addWidget(glyph)
        root.addLayout(top)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("MetricValue")
        self.value_label.setProperty("accent", accent)
        root.addWidget(self.value_label)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("MetricSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        root.addWidget(self.subtitle_label)
        self.refresh_metrics()

    def refresh_metrics(self) -> None:
        """Keep cards readable when the application font is enlarged."""
        line_height = max(self.fontMetrics().lineSpacing(), 16)
        self.setMinimumHeight(max(118, 60 + (line_height * 3)))

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().changeEvent(event)
        if event.type() in {QEvent.Type.FontChange, QEvent.Type.StyleChange}:
            QTimer.singleShot(0, self.refresh_metrics)

    def set_value(self, value: str, subtitle: str | None = None) -> None:
        self.value_label.setText(value)
        if subtitle is not None:
            self.subtitle_label.setText(subtitle)


class InfoBanner(QFrame):
    def __init__(self, text: str, tone: str = "info", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("InfoBanner")
        self.setProperty("tone", tone)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(10)
        glyph = QLabel()
        color = {"info": "#2563eb", "warning": "#d97706", "danger": "#dc2626", "success": "#16a34a"}.get(tone, "#2563eb")
        glyph.setPixmap(icon("warning" if tone in {"warning", "danger"} else "check", color, 18).pixmap(18, 18))
        layout.addWidget(glyph, 0, Qt.AlignTop)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("InfoBannerText")
        layout.addWidget(label, 1)


class ToastNotification(QFrame):
    """Temporary, non-modal notification displayed over a page."""

    closed = Signal()

    def __init__(self, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ToastNotification")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet(
            """
            QFrame#ToastNotification {
                background: #dcfce7;
                border: 1px solid #86efac;
                border-radius: 10px;
            }
            QLabel#ToastIcon, QLabel#ToastMessage {
                color: #166534;
            }
            QLabel#ToastIcon {
                font-size: 16px;
                font-weight: 800;
            }
            QLabel#ToastMessage {
                font-weight: 650;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(8)
        icon_label = QLabel("✓")
        icon_label.setObjectName("ToastIcon")
        layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        message_label = QLabel(message)
        message_label.setObjectName("ToastMessage")
        message_label.setWordWrap(True)
        message_label.setMaximumWidth(420)
        layout.addWidget(message_label, 1)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._animation = QPropertyAnimation(self._opacity, b"opacity", self)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.finished.connect(self._finish)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._closing = False

    def show_toast(self, duration: int = 2400) -> None:
        self.adjustSize()
        self._position()
        self._opacity.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(duration)

    def _position(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 24
        x = max(margin, parent.width() - self.width() - margin)
        self.move(x, margin)

    def reposition(self) -> None:
        """Keep the toast anchored to the page after a window resize."""
        if self.isVisible():
            self._position()

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._animation.stop()
        self.hide()
        self.closed.emit()
        self.deleteLater()

    def _fade_out(self) -> None:
        if self._closing:
            return
        self._animation.setDuration(450)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.start()

    def _finish(self) -> None:
        self.dismiss()



def _update_table_metrics(table: QTableWidget) -> None:
    """Adjust table rows and headers to the active font without clipping text."""
    line_height = max(table.fontMetrics().lineSpacing(), 15)
    row_height = max(38, line_height + 20)
    header_height = max(38, line_height + 20)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.verticalHeader().setMinimumSectionSize(row_height)
    table.horizontalHeader().setMinimumHeight(header_height)


class _AdaptiveTableEventFilter(QObject):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.StyleChange,
            QEvent.Type.Polish,
        }:
            QTimer.singleShot(0, lambda table=watched: _update_table_metrics(table))
        return False


def refresh_adaptive_metrics(root: QWidget) -> None:
    """Recalculate size-sensitive widgets after a global font change."""
    if isinstance(root, QTableWidget):
        _update_table_metrics(root)
    for table in root.findChildren(QTableWidget):
        _update_table_metrics(table)
    if isinstance(root, MetricCard):
        root.refresh_metrics()
    for card in root.findChildren(MetricCard):
        card.refresh_metrics()
    root.updateGeometry()


def configure_table(
    table: QTableWidget,
    headers: Sequence[str],
    *,
    editable: bool = False,
    stretch_last: bool = True,
) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    if not editable:
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    _update_table_metrics(table)
    adaptive_filter = _AdaptiveTableEventFilter(table)
    table.installEventFilter(adaptive_filter)
    table._adaptive_metrics_filter = adaptive_filter  # type: ignore[attr-defined]
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setMinimumSectionSize(70)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    if stretch_last:
        table.horizontalHeader().setStretchLastSection(True)
    table.setSortingEnabled(False)


def fill_table(
    table: QTableWidget,
    rows: Iterable[Sequence[object]],
    *,
    user_role_column: int | None = None,
    user_role_values: Sequence[object] | None = None,
) -> None:
    materialized = list(rows)
    table.setSortingEnabled(False)
    table.setRowCount(len(materialized))
    for row_index, values in enumerate(materialized):
        for col_index, value in enumerate(values):
            item = QTableWidgetItem(str(value if value is not None else ""))
            if (
                user_role_column is not None
                and col_index == user_role_column
                and user_role_values is not None
            ):
                item.setData(Qt.UserRole, user_role_values[row_index])
            table.setItem(row_index, col_index, item)
    table.setSortingEnabled(True)


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget:
            widget.deleteLater()
        elif child_layout:
            clear_layout(child_layout)


def status_color(status: str) -> QColor:
    normalized = status.lower()
    app = QApplication.instance()
    dark = bool(app and app.property("theme_name") == "Oscuro")
    if normalized in {"finalizado", "pagado", "pagada", "activo"}:
        return QColor("#71d897" if dark else "#15803d")
    if normalized in {"vencido", "inactivo"}:
        return QColor("#ff8d8d" if dark else "#b91c1c")
    if normalized in {"en progreso", "medido"}:
        return QColor("#8ab4f8" if dark else "#1d4ed8")
    if normalized == "confirmado":
        return QColor("#c1a7ff" if dark else "#7c3aed")
    return QColor("#f4c56a" if dark else "#b45309")
