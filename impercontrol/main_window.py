from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QDate, QEvent, QSize, QTimer, Qt
from PySide6.QtGui import QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .branding import APP_NAME, APP_SUBTITLE, APP_VERSION, LOGO_ICO_PATH, SIDEBAR_SUBTITLE
from .context import ApplicationContext
from .icons import icon
from .pages import (
    BrigadesPage,
    CashPage,
    ClientsPage,
    DashboardPage,
    DebtsPage,
    ExpensesPage,
    FinancialReportsPage,
    IncomesPage,
    JobsPage,
    LoansPage,
    MaterialsPage,
    MaterialSalesPage,
    MeasurementsPage,
    ReportsPage,
    SettingsPage,
)
from .ui_components import button, refresh_adaptive_metrics


@dataclass(slots=True)
class PageDefinition:
    name: str
    icon_name: str
    hint: str
    page: QWidget
    group: str = "GESTIÓN"


class MainWindow(QMainWindow):
    def __init__(self, context: ApplicationContext) -> None:
        super().__init__()
        self.context = context
        self.repo = context.repository
        self._font_increment = self.repo.setting_int("font_size_increment", 0)
        self.setWindowTitle(f"{APP_NAME} — {APP_SUBTITLE}")
        if LOGO_ICO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_ICO_PATH)))

        # Tamaño inicial adaptado al escritorio útil. En una pantalla 1080p con
        # escalado de Windows la ventana conserva espacio para la barra de tareas.
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(1440, max(1000, int(available.width() * 0.92)))
            height = min(900, max(660, int(available.height() * 0.88)))
            self.resize(width, height)
            self.move(
                available.x() + max((available.width() - width) // 2, 0),
                available.y() + max((available.height() - height) // 2, 0),
            )
        else:
            self.resize(1360, 820)
        self.setMinimumSize(960, 640)

        app_root = QWidget()
        app_root.setObjectName("AppRoot")
        root = QHBoxLayout(app_root)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(app_root)

        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.top_bar = self._build_top_bar()
        content_layout.addWidget(self.top_bar)

        page_container = QWidget()
        page_layout = QVBoxLayout(page_container)
        page_layout.setContentsMargins(18, 14, 18, 18)
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageStack")
        page_layout.addWidget(self.stack)
        content_layout.addWidget(page_container, 1)
        root.addWidget(content, 1)

        self._create_pages()
        self.refresh_font_layout()
        QTimer.singleShot(0, self.refresh_font_layout)
        self.statusBar().showMessage(f"{APP_NAME} listo")
        self.nav_buttons[0].setChecked(True)
        self.show_page(0)
        self._apply_responsive_visibility()

        # Revisa periódicamente las fechas de inicio para que un trabajo pase
        # a En Progreso aunque la aplicación permanezca abierta durante el día.
        self.workflow_timer = QTimer(self)
        self.workflow_timer.setInterval(5 * 60 * 1000)
        self.workflow_timer.timeout.connect(self.refresh_workflow_states)
        self.workflow_timer.start()

    def refresh_workflow_states(self) -> None:
        if self.repo.advance_due_jobs() > 0:
            self.refresh_all()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(248)
        sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(8)

        # El encabezado queda fuera del área desplazable y tiene altura fija.
        # De esta manera nunca se aplasta cuando la ventana tiene poca altura.
        brand = QFrame()
        self.brand_block = brand
        brand.setObjectName("BrandBlock")
        brand.setMinimumHeight(82)
        brand.setMaximumHeight(82)
        brand.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(11, 10, 11, 10)
        brand_layout.setSpacing(10)

        mark = QLabel()
        self.logo_mark = mark
        mark.setObjectName("LogoImage")
        mark.setFixedSize(48, 48)
        mark.setAlignment(Qt.AlignCenter)
        if LOGO_ICO_PATH.exists():
            mark.setPixmap(QIcon(str(LOGO_ICO_PATH)).pixmap(44, 44))
        else:
            mark.setText("D&Y")
        brand_layout.addWidget(mark, 0, Qt.AlignVCenter)

        text_host = QWidget()
        text_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text = QVBoxLayout(text_host)
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        title = QLabel(APP_NAME)
        self.brand_title = title
        title.setObjectName("LogoTitle")
        title.setWordWrap(False)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        subtitle = QLabel(SIDEBAR_SUBTITLE)
        self.brand_subtitle = subtitle
        subtitle.setObjectName("LogoSubtitle")
        subtitle.setWordWrap(False)
        subtitle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        text.addWidget(title)
        text.addWidget(subtitle)
        brand_layout.addWidget(text_host, 1)
        layout.addWidget(brand)

        # La navegación sí puede desplazarse verticalmente en laptops o al usar
        # tamaños de fuente grandes. No se muestra barra horizontal.
        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("SidebarScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        nav_host = QWidget()
        nav_host.setObjectName("SidebarNavHost")
        self.nav_layout = QVBoxLayout(nav_host)
        self.nav_layout.setContentsMargins(0, 4, 0, 4)
        self.nav_layout.setSpacing(4)
        nav_scroll.setWidget(nav_host)
        layout.addWidget(nav_scroll, 1)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []

        self.sidebar_footer = QLabel(
            f"Base local SQLite\nGestión operativa · v{APP_VERSION}"
        )
        self.sidebar_footer.setObjectName("FooterText")
        self.sidebar_footer.setAlignment(Qt.AlignCenter)
        self.sidebar_footer.setWordWrap(True)
        self.sidebar_footer.setMinimumHeight(38)
        self.sidebar_footer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.sidebar_footer)
        return sidebar

    def _build_top_bar(self) -> QFrame:
        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(24, 13, 24, 13)
        layout.setSpacing(14)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("PageTitle")
        self.page_hint = QLabel("Control general del negocio")
        self.page_hint.setObjectName("HeaderHint")
        title_col.addWidget(self.page_title)
        title_col.addWidget(self.page_hint)
        layout.addLayout(title_col)
        layout.addStretch()

        today = QDate.currentDate().toString("dd/MM/yyyy")
        self.date_label = QLabel(f"  {today}")
        self.date_label.setObjectName("DatabaseBadge")
        self.date_label.setPixmap(icon("calendar", "#31527a", 16).pixmap(16, 16))
        # QLabel no permite icono y texto de forma nativa; el texto es la
        # información principal y el icono conserva la jerarquía visual.
        self.date_label.setText(f"  {today}")
        layout.addWidget(self.date_label)

        self.quick_measurement = button("Nueva medición", "plus", "primary")
        self.quick_measurement.clicked.connect(
            lambda: self.show_page_by_name("Mediciones", clear=True)
        )
        layout.addWidget(self.quick_measurement)

        self.db_label = QLabel("Base local · SQLite")
        self.db_label.setObjectName("DatabaseBadge")
        layout.addWidget(self.db_label)
        return top_bar

    def _create_pages(self) -> None:
        self.pages: list[PageDefinition] = [
            PageDefinition("Dashboard", "dashboard", "Resumen financiero, trabajos y alertas de mantenimiento", DashboardPage(self.context), "PRINCIPAL"),
            PageDefinition("Clientes", "clients", "Historial de clientes con cada techo separado", ClientsPage(self.context), "GESTIÓN"),
            PageDefinition("Mediciones", "measure", "Medidas de WhatsApp, datos del cliente y presupuesto", MeasurementsPage(self.context), "GESTIÓN"),
            PageDefinition("Trabajos", "jobs", "Medidos, confirmados, en ejecución y finalizados", JobsPage(self.context), "GESTIÓN"),
            PageDefinition("Brigadas", "brigades", "Trabajadores, roles, sustituciones y rendimiento", BrigadesPage(self.context), "OPERACIÓN"),
            PageDefinition("Materiales", "materials", "Inventario, compras a crédito, pagos y consumos", MaterialsPage(self.context), "OPERACIÓN"),
            PageDefinition("Venta de materiales", "money", "Ventas directas de pintura y malla con descuento automático de stock", MaterialSalesPage(self.context), "OPERACIÓN"),
            PageDefinition("Caja", "money", "Libro de caja, entradas externas y movimientos de efectivo", CashPage(self.context), "FINANZAS"),
            PageDefinition("Ingresos", "income", "Historial de anticipos y cobros de trabajos", IncomesPage(self.context), "FINANZAS"),
            PageDefinition("Préstamos", "money", "Dinero prestado, abonos y saldos por cobrar", LoansPage(self.context), "FINANZAS"),
            PageDefinition("Deudas", "expense", "Personas, empresas, compras a crédito y pagos", DebtsPage(self.context), "FINANZAS"),
            PageDefinition("Gastos", "expense", "Gastos generales y asociados a trabajos", ExpensesPage(self.context), "FINANZAS"),
            PageDefinition("Reportes de trabajadores", "reports", "Rendimiento por brigada y trabajador", ReportsPage(self.context), "ANÁLISIS"),
            PageDefinition("Reporte financiero", "reports", "Análisis por período y exportación a PDF", FinancialReportsPage(self.context), "ANÁLISIS"),
            PageDefinition("Configuración", "settings", "Precios, tarifas, temas, alertas y copias de seguridad", SettingsPage(self.context), "SISTEMA"),
        ]

        last_group = None
        for index, definition in enumerate(self.pages):
            if definition.group != last_group:
                section = QLabel(definition.group)
                section.setObjectName("NavSection")
                self.nav_layout.addWidget(section)
                last_group = definition.group
            nav = QPushButton(definition.name)
            nav.setObjectName("NavButton")
            nav.setCheckable(True)
            nav.setToolTip(definition.name)
            nav.setAccessibleName(definition.name)
            nav.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            nav.setIcon(icon(definition.icon_name, "#52647a", 18))
            nav.setIconSize(nav.iconSize())
            nav.clicked.connect(lambda checked=False, idx=index: self.show_page(idx))
            self.button_group.addButton(nav, index)
            self.nav_buttons.append(nav)
            self.nav_layout.addWidget(nav)
            self.stack.addWidget(definition.page)
            definition.page.data_changed.connect(self.refresh_all)

        self.nav_layout.addStretch()

    def changeEvent(self, event) -> None:  # noqa: N802 - nombre requerido por Qt
        super().changeEvent(event)
        if event.type() in {QEvent.Type.FontChange, QEvent.Type.StyleChange}:
            QTimer.singleShot(0, self.refresh_font_layout)

    def refresh_font_layout(self) -> None:
        """Recalculate widths and heights after changing the global font size."""
        if not hasattr(self, "sidebar"):
            return
        self._font_increment = self.repo.setting_int("font_size_increment", self._font_increment)
        app_font = QApplication.font()
        metrics = QFontMetrics(app_font)

        page_names = [definition.name for definition in getattr(self, "pages", [])]
        longest_nav = max((metrics.horizontalAdvance(name) for name in page_names), default=150)
        brand_text = max(
            metrics.horizontalAdvance(APP_NAME),
            metrics.horizontalAdvance(SIDEBAR_SUBTITLE),
        )
        # Icon + internal padding + sidebar margins. The upper limit keeps enough
        # room for the main content even in a 1080p laptop window.
        required_nav_width = longest_nav + 92
        required_brand_width = brand_text + 98
        target_width = max(248, required_nav_width, required_brand_width)
        maximum_width = max(248, min(400, int(max(self.width(), 960) * 0.42)))
        self.sidebar.setFixedWidth(min(target_width, maximum_width))

        line_height = max(metrics.lineSpacing(), 16)
        nav_height = max(42, line_height + 22)
        icon_size = min(24, 18 + max(self._font_increment, 0))
        for nav in getattr(self, "nav_buttons", []):
            nav.setMinimumHeight(nav_height)
            nav.setIconSize(QSize(icon_size, icon_size))
            nav.updateGeometry()

        brand_height = max(82, 78 + max(self._font_increment, 0) * 4)
        if hasattr(self, "brand_block"):
            self.brand_block.setMinimumHeight(brand_height)
            self.brand_block.setMaximumHeight(brand_height)
        if hasattr(self, "logo_mark"):
            mark_size = min(62, 48 + max(self._font_increment, 0) * 2)
            self.logo_mark.setFixedSize(mark_size, mark_size)
            if LOGO_ICO_PATH.exists():
                self.logo_mark.setPixmap(QIcon(str(LOGO_ICO_PATH)).pixmap(mark_size - 4, mark_size - 4))
        if hasattr(self, "sidebar_footer"):
            self.sidebar_footer.setMinimumHeight(max(38, line_height * 2 + 12))

        refresh_adaptive_metrics(self)
        self._apply_responsive_visibility()
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - nombre requerido por Qt
        super().resizeEvent(event)
        self._apply_responsive_visibility()

    def _apply_responsive_visibility(self) -> None:
        """Hide secondary header elements before larger fonts can overlap them."""
        content_width = self.width() - (self.sidebar.width() if hasattr(self, "sidebar") else 0)
        extra = max(self._font_increment, 0) * 18
        if hasattr(self, "db_label"):
            self.db_label.setVisible(content_width >= 930 + extra)
        if hasattr(self, "date_label"):
            self.date_label.setVisible(content_width >= 800 + extra)
        if hasattr(self, "page_hint"):
            self.page_hint.setVisible(content_width >= 690 + extra)
        if hasattr(self, "quick_measurement"):
            self.quick_measurement.setVisible(content_width >= 610 + extra)

    def show_page(self, index: int) -> None:
        if index < 0 or index >= len(self.pages):
            return
        self.stack.setCurrentIndex(index)
        definition = self.pages[index]
        self.page_title.setText(definition.name)
        self.page_hint.setText(definition.hint)
        self.nav_buttons[index].setChecked(True)
        definition.page.refresh()
        self.statusBar().showMessage(f"Sección: {definition.name}", 2500)

    def show_page_by_name(self, name: str, clear: bool = False) -> None:
        for index, definition in enumerate(self.pages):
            if definition.name == name:
                self.show_page(index)
                if clear and isinstance(definition.page, MeasurementsPage):
                    definition.page.clear_form()
                return

    def refresh_all(self) -> None:
        for definition in self.pages:
            definition.page.refresh()
