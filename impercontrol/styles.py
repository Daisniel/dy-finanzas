APP_STYLE = r"""
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    color: #18243a;
}
QMainWindow, QWidget#AppRoot, QStackedWidget#PageStack {
    background: #f4f7fb;
}
QToolTip {
    background: #172033;
    color: #ffffff;
    border: 0;
    padding: 6px 9px;
    border-radius: 5px;
}
QFrame#Sidebar {
    background: #ffffff;
    border-right: 1px solid #dfe6f0;
}
QFrame#BrandBlock {
    background: #eff6ff;
    border: 1px solid #dbeafe;
    border-radius: 12px;
}
QLabel#LogoMark {
    background: #2563eb;
    color: white;
    border-radius: 10px;
    font-size: 17px;
    font-weight: 800;
}
QLabel#LogoImage {
    background: transparent;
    border: 0;
}
QLabel#LogoTitle {
    color: #0f2d57;
    font-size: 18px;
    font-weight: 800;
}
QLabel#LogoSubtitle, QLabel#Muted, QLabel#PanelSubtitle,
QLabel#MetricSubtitle, QLabel#HeaderHint, QLabel#FooterText {
    color: #6b778c;
}
QLabel#NavSection {
    color: #94a0b4;
    font-size: 11px;
    font-weight: 700;
    padding: 9px 11px 4px 11px;
}
QPushButton#NavButton {
    background: transparent;
    border: 0;
    border-radius: 9px;
    text-align: left;
    padding: 10px 12px;
    min-height: 22px;
    color: #41516a;
    font-weight: 600;
}
QPushButton#NavButton:hover {
    background: #f0f6ff;
    color: #1d4ed8;
}
QPushButton#NavButton:checked {
    background: #e8f1ff;
    color: #1d4ed8;
    font-weight: 700;
}
QFrame#TopBar {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
}
QLabel#PageTitle {
    color: #152238;
    font-size: 25px;
    font-weight: 800;
}
QLabel#HeaderHint {
    font-size: 12px;
}
QLabel#DatabaseBadge {
    color: #31527a;
    background: #edf5ff;
    border: 1px solid #d5e7ff;
    border-radius: 9px;
    padding: 7px 10px;
    font-size: 12px;
    font-weight: 600;
}
QFrame#Panel, QFrame#MetricCard, QGroupBox {
    background: #ffffff;
    border: 1px solid #dfe6f0;
    border-radius: 12px;
}
QFrame#Panel:hover, QFrame#MetricCard:hover {
    border-color: #c8d8ee;
}
QLabel#PanelTitle {
    color: #1b2b43;
    font-size: 15px;
    font-weight: 750;
}
QLabel#PanelSubtitle {
    font-size: 12px;
}
QLabel#MaterialsEstimate {
    font-size: 14px;
}
QLabel#MetricTitle {
    color: #66748a;
    font-weight: 650;
}
QLabel#MetricValue {
    color: #1d4ed8;
    font-size: 24px;
    font-weight: 800;
}
QLabel#MetricValue[accent="green"] { color: #15803d; }
QLabel#MetricValue[accent="red"] { color: #b91c1c; }
QLabel#MetricValue[accent="amber"] { color: #b45309; }
QLabel#MetricValue[accent="purple"] { color: #6d28d9; }
QLabel#MetricValue[accent="cyan"] { color: #0e7490; }
QLabel#MetricIcon {
    background: #eff6ff;
    border-radius: 9px;
}
QFrame#MetricCard[accent="green"] QLabel#MetricIcon { background: #ecfdf3; }
QFrame#MetricCard[accent="red"] QLabel#MetricIcon { background: #fef2f2; }
QFrame#MetricCard[accent="amber"] QLabel#MetricIcon { background: #fffbeb; }
QFrame#MetricCard[accent="purple"] QLabel#MetricIcon { background: #f5f3ff; }
QFrame#MetricCard[accent="cyan"] QLabel#MetricIcon { background: #ecfeff; }
QFrame#InfoBanner {
    background: #eff6ff;
    border: 1px solid #dbeafe;
    border-radius: 10px;
}
QFrame#InfoBanner[tone="warning"] {
    background: #fffbeb;
    border-color: #fde68a;
}
QFrame#InfoBanner[tone="danger"] {
    background: #fef2f2;
    border-color: #fecaca;
}
QFrame#InfoBanner[tone="success"] {
    background: #f0fdf4;
    border-color: #bbf7d0;
}
QLabel#InfoBannerText {
    color: #38506f;
}
QGroupBox {
    margin-top: 16px;
    padding: 20px 16px 16px 16px;
    font-weight: 700;
    color: #1b2b43;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 15px;
    padding: 0 7px;
    background: #ffffff;
    color: #31527a;
    font-weight: 700;
}
QLabel#FieldLabel {
    color: #4f5f75;
    font-weight: 650;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit,
QDoubleSpinBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #cfd9e7;
    border-radius: 8px;
    padding: 7px 9px;
    min-height: 20px;
    selection-background-color: #bfdbfe;
}
QTextEdit, QPlainTextEdit {
    padding: 9px;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover,
QDateEdit:hover, QDoubleSpinBox:hover, QSpinBox:hover {
    border-color: #9db8dc;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QDateEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #2563eb;
}
QComboBox::drop-down, QDateEdit::drop-down {
    border: 0;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d8e1ed;
    selection-background-color: #e8f1ff;
    selection-color: #1d4ed8;
    outline: 0;
}
QPushButton {
    background: #ffffff;
    color: #245caa;
    border: 1px solid #b9cde9;
    border-radius: 8px;
    padding: 8px 13px;
    min-height: 20px;
    font-weight: 650;
}
QPushButton:hover {
    background: #f1f7ff;
    border-color: #8eb4e5;
}
QPushButton:pressed {
    background: #e4effd;
}
QPushButton[role="primary"], QPushButton#Primary {
    background: #2563eb;
    color: #ffffff;
    border-color: #2563eb;
}
QPushButton[role="primary"]:hover, QPushButton#Primary:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
}
QPushButton[role="danger"], QPushButton#Danger {
    color: #b91c1c;
    border-color: #f0b7b7;
    background: #fffafa;
}
QPushButton[role="danger"]:hover, QPushButton#Danger:hover {
    background: #fef2f2;
    border-color: #ef9999;
}
QPushButton[role="ghost"] {
    background: transparent;
    border-color: transparent;
}
QPushButton[role="ghost"]:hover {
    background: #eef4fb;
}
QPushButton:disabled {
    color: #a6b0bf;
    background: #f3f5f8;
    border-color: #e3e7ed;
}
QTableWidget {
    background: #ffffff;
    border: 1px solid #dfe6f0;
    border-radius: 9px;
    alternate-background-color: #f8fafc;
    selection-background-color: #e6f0ff;
    selection-color: #14233a;
    outline: 0;
}
QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #eef2f7;
}
QTableWidget::item:selected {
    background: #e6f0ff;
    color: #14233a;
}
QHeaderView::section {
    background: #f1f5f9;
    color: #4a5a70;
    padding: 9px 8px;
    border: 0;
    border-right: 1px solid #e2e8f0;
    border-bottom: 1px solid #dfe6f0;
    font-weight: 700;
}
QTabWidget::pane {
    border: 1px solid #dfe6f0;
    background: #ffffff;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #66748a;
    padding: 10px 17px;
    margin-right: 3px;
    border-bottom: 2px solid transparent;
    font-weight: 650;
}
QTabBar::tab:hover {
    color: #1d4ed8;
    background: #f5f9ff;
}
QTabBar::tab:selected {
    color: #1d4ed8;
    border-bottom: 2px solid #2563eb;
    font-weight: 750;
}
QDialog {
    background: #f4f7fb;
}
QDialogButtonBox QPushButton {
    min-width: 100px;
}
QScrollArea {
    border: 0;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QAbstractScrollArea::corner {
    background: transparent;
    border: 0;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
    border: 0;
}
QScrollBar::handle:vertical {
    background: #bac6d6;
    border-radius: 5px;
    min-height: 34px;
}
QScrollBar::handle:vertical:hover { background: #9cabbf; }
QScrollBar::horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
    border: 0;
}
QScrollBar::handle:horizontal {
    background: #bac6d6;
    border-radius: 5px;
    min-width: 34px;
}
QScrollBar::handle:horizontal:hover { background: #9cabbf; }
/* Las flechas laterales se eliminan globalmente. Evita los trazos o símbolos
   incompletos que algunos temas de Windows dibujan en tablas y formularios. */
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: transparent;
    border: 0;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: transparent;
    border: 0;
}
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {
    width: 0px;
    height: 0px;
    background: transparent;
    border: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
    border: 0;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #e2e8f0;
    color: #68778c;
}
QStatusBar::item { border: 0; }

/* Numeric fields are typed manually. Hide ambiguous increment/decrement controls. */
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}
"""


THEME_NAMES = ["Claro", "Oscuro", "Azul pastel", "Verde salvia"]

THEME_OVERRIDES = {
    "Claro": "",
    "Azul pastel": r"""
* { color: #233a57; }
QMainWindow, QWidget#AppRoot, QStackedWidget#PageStack, QDialog { background: #edf5fc; }
QFrame#Sidebar, QFrame#TopBar, QFrame#Panel, QFrame#MetricCard, QGroupBox,
QTableWidget, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit,
QDoubleSpinBox, QSpinBox, QTabWidget::pane { background: #f9fcff; }
QFrame#Sidebar { border-right-color: #cbddee; }
QFrame#TopBar { border-bottom-color: #cbddee; }
QFrame#BrandBlock { background: #dcecff; border-color: #bfd8f5; }
QPushButton#NavButton:checked { background: #d9eaff; color: #315f9f; }
QPushButton#NavButton:hover { background: #e5f1ff; color: #315f9f; }
QPushButton[role="primary"], QPushButton#Primary { background: #6f9ed6; border-color: #6f9ed6; }
QPushButton[role="primary"]:hover, QPushButton#Primary:hover { background: #5e8dc5; border-color: #5e8dc5; }
QLabel#MetricValue { color: #466f9f; }
QLabel#DatabaseBadge, QFrame#InfoBanner { background: #e1effd; border-color: #c1d9f1; }
QTableWidget { alternate-background-color: #f0f7fd; selection-background-color: #d6e8fa; }
QHeaderView::section { background: #e7f1fa; border-bottom-color: #cbddee; }
QStatusBar { background: #f9fcff; border-top-color: #cbddee; }
""",
    "Verde salvia": r"""
* { color: #2f4236; }
QMainWindow, QWidget#AppRoot, QStackedWidget#PageStack, QDialog { background: #f1f5ef; }
QFrame#Sidebar, QFrame#TopBar, QFrame#Panel, QFrame#MetricCard, QGroupBox,
QTableWidget, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit,
QDoubleSpinBox, QSpinBox, QTabWidget::pane { background: #fbfdf9; }
QFrame#Sidebar { border-right-color: #d4dfd1; }
QFrame#TopBar { border-bottom-color: #d4dfd1; }
QFrame#BrandBlock { background: #e4eee1; border-color: #c9dbc5; }
QPushButton#NavButton:checked { background: #dcebd8; color: #416b4c; }
QPushButton#NavButton:hover { background: #e7f1e4; color: #416b4c; }
QPushButton[role="primary"], QPushButton#Primary { background: #64866d; border-color: #64866d; }
QPushButton[role="primary"]:hover, QPushButton#Primary:hover { background: #55775f; border-color: #55775f; }
QLabel#MetricValue { color: #4f7459; }
QLabel#DatabaseBadge, QFrame#InfoBanner { background: #e7f1e4; border-color: #cadcc6; }
QTableWidget { alternate-background-color: #f3f7f1; selection-background-color: #dcebd8; }
QHeaderView::section { background: #eaf1e7; border-bottom-color: #d4dfd1; }
QStatusBar { background: #fbfdf9; border-top-color: #d4dfd1; }
""",
    "Oscuro": r"""
* { color: #dbe7f5; }
QMainWindow, QWidget#AppRoot, QStackedWidget#PageStack, QDialog,
QScrollArea > QWidget > QWidget { background: #111827; }
QFrame#Sidebar, QFrame#TopBar, QFrame#Panel, QFrame#MetricCard, QGroupBox,
QTabWidget::pane, QStatusBar { background: #182235; border-color: #2d3b52; }
QFrame#Sidebar { border-right-color: #2d3b52; }
QFrame#TopBar { border-bottom-color: #2d3b52; }
QFrame#BrandBlock { background: #22314a; border-color: #344862; }
QLabel#LogoTitle, QLabel#PageTitle, QLabel#PanelTitle, QLabel#FieldLabel,
QGroupBox, QGroupBox::title { color: #f0f6ff; background: transparent; }
QLabel#LogoSubtitle, QLabel#Muted, QLabel#PanelSubtitle, QLabel#MetricSubtitle,
QLabel#HeaderHint, QLabel#FooterText, QLabel#MetricTitle { color: #9fb0c6; }
QLabel#DatabaseBadge { color: #c9dcf5; background: #22314a; border-color: #344862; }
QPushButton#NavButton { color: #b8c7da; }
QPushButton#NavButton:hover { background: #22314a; color: #8ab4f8; }
QPushButton#NavButton:checked { background: #263a5a; color: #a8c8ff; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit,
QDoubleSpinBox, QSpinBox { background: #111a2a; border-color: #3a4a62; color: #e7eef8; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QDateEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus { border-color: #6ea8fe; }
QComboBox QAbstractItemView { background: #182235; border-color: #3a4a62; color: #e7eef8; selection-background-color: #2d4f7c; selection-color: #ffffff; }
QPushButton { background: #1d2b40; color: #bcd5f8; border-color: #405775; }
QPushButton:hover { background: #263a55; border-color: #5f7fa7; }
QPushButton[role="primary"], QPushButton#Primary { background: #3978c5; border-color: #3978c5; color: #ffffff; }
QPushButton[role="primary"]:hover, QPushButton#Primary:hover { background: #4b8bd8; border-color: #4b8bd8; }
QPushButton[role="danger"], QPushButton#Danger { background: #3a2026; color: #ffb4b4; border-color: #7a414a; }
QFrame#InfoBanner { background: #1e3552; border-color: #35577e; }
QFrame#InfoBanner[tone="warning"] { background: #3b321b; border-color: #6f5a24; }
QFrame#InfoBanner[tone="danger"] { background: #3a2026; border-color: #7a414a; }
QFrame#InfoBanner[tone="success"] { background: #193629; border-color: #2e6a4d; }
QLabel#InfoBannerText { color: #c6d7ec; }
QTableWidget { background: #182235; border-color: #2d3b52; alternate-background-color: #141e2f; selection-background-color: #29466d; selection-color: #ffffff; gridline-color: #2b394d; }
QTableWidget::item { border-bottom-color: #243248; }
QHeaderView::section { background: #22314a; color: #dbe7f5; border-bottom-color: #3a4a62; border-right-color: #2d3b52; }
QTabBar::tab { color: #9fb0c6; }
QTabBar::tab:hover { color: #a8c8ff; background: #22314a; }
QTabBar::tab:selected { color: #a8c8ff; border-bottom-color: #6ea8fe; }
QLabel#MetricValue { color: #8ab4f8; }
QLabel#MetricValue[accent="green"] { color: #71d897; }
QLabel#MetricValue[accent="red"] { color: #ff8d8d; }
QLabel#MetricValue[accent="amber"] { color: #f4c56a; }
QLabel#MetricValue[accent="purple"] { color: #c1a7ff; }
QLabel#MetricValue[accent="cyan"] { color: #78d6df; }
QLabel#MetricIcon, QFrame#MetricCard[accent="green"] QLabel#MetricIcon,
QFrame#MetricCard[accent="red"] QLabel#MetricIcon,
QFrame#MetricCard[accent="amber"] QLabel#MetricIcon,
QFrame#MetricCard[accent="purple"] QLabel#MetricIcon,
QFrame#MetricCard[accent="cyan"] QLabel#MetricIcon { background: #22314a; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #52637a; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #70839e; }
QToolTip { background: #e6eef8; color: #111827; }
""",
}


def build_app_style(font_increment: int = 0, theme_name: str = "Claro") -> str:
    """Build the selected theme and scale explicit font sizes consistently."""
    import re

    theme = theme_name if theme_name in THEME_OVERRIDES else "Claro"
    style = APP_STYLE + THEME_OVERRIDES[theme]
    increment = max(-2, min(int(font_increment), 6))
    if increment == 0:
        return style
    return re.sub(
        r"font-size:\s*(\d+)px",
        lambda match: f"font-size: {max(int(match.group(1)) + increment, 8)}px",
        style,
    )
