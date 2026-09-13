from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


# SVGs minimalistas incrustados. No se distribuyen archivos externos.
_PATHS: dict[str, str] = {
    "dashboard": '<path d="M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z"/>',
    "clients": '<path d="M16 11c1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3 1.34 3 3 3ZM8 11c1.66 0 3-1.34 3-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3Zm8 2c-2 0-6 1-6 3v3h12v-3c0-2-4-3-6-3ZM8 13c-2.33 0-7 1.17-7 3.5V19h7v-3c0-.85.33-1.59.92-2.23A7.94 7.94 0 0 0 8 13Z"/>',
    "measure": '<path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25Zm17.71-10.04a1.003 1.003 0 0 0 0-1.42l-2.5-2.5a1.003 1.003 0 0 0-1.42 0l-1.96 1.96 3.75 3.75 2.13-1.79Z"/>',
    "jobs": '<path d="M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-2 .89-2 2v11c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2Zm-10-2h4v2h-4V4Zm10 15H4v-5h6v1h4v-1h6v5Zm-8-5H4V8h16v6h-8Z"/>',
    "brigades": '<path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4Zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4Z"/>',
    "materials": '<path d="M21 8.5 12 3 3 8.5v7L12 21l9-5.5v-7ZM12 5.34 18.75 9 12 12.66 5.25 9 12 5.34ZM5 10.7l6 3.25v4.47l-6-3.67V10.7Zm8 7.72v-4.47l6-3.25v4.05l-6 3.67Z"/>',
    "income": '<path d="M11 8.5h2V7h1.5a2.5 2.5 0 0 1 0 5H11a.5.5 0 0 0 0 1h3.5a4.5 4.5 0 0 1 0 9H13v1.5h-2V22h-1.5a4.5 4.5 0 0 1-4.5-4.5h2A2.5 2.5 0 0 0 9.5 20h5a2.5 2.5 0 0 0 0-5H11a2.5 2.5 0 0 1 0-5h3.5a.5.5 0 0 0 0-1H11a2.5 2.5 0 0 0-2.5 2.5h-2A4.5 4.5 0 0 1 11 7V5.5h2V7h1.5A2.5 2.5 0 0 1 17 9.5h-2A.5.5 0 0 0 14.5 9H11a.5.5 0 0 0 0 1Z"/>',
    "expense": '<path d="M19 13H5v-2h14v2Zm0-6H5v2h14V7Zm-6 8H5v2h8v-2Zm8 0h-6v6h6v-6Z"/>',
    "reports": '<path d="M3 3v18h18v-2H5V3H3Zm4 12h2v2H7v-2Zm0-4h2v3H7v-3Zm4-4h2v10h-2V7Zm4 3h2v7h-2v-7Zm4-5h2v12h-2V5Z"/>',
    "settings": '<path d="M19.43 12.98c.04-.32.07-.65.07-.98s-.02-.66-.07-.98l2.11-1.65-2-3.46-2.49 1a7.1 7.1 0 0 0-1.69-.98L15 3.27h-4l-.4 2.66c-.61.25-1.17.59-1.69.98l-2.49-1-2 3.46 2.11 1.65c-.04.32-.08.66-.08.98s.03.66.08.98l-2.11 1.65 2 3.46 2.49-1c.52.4 1.08.73 1.69.98l.4 2.66h4l.4-2.66c.61-.25 1.17-.58 1.69-.98l2.49 1 2-3.46-2.11-1.65ZM13 15.5A3.5 3.5 0 1 1 13 8a3.5 3.5 0 0 1 0 7.5Z"/>',
    "plus": '<path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2Z"/>',
    "save": '<path d="M17 3H5a2 2 0 0 0-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4Zm0 2.5L18.5 7H17V5.5ZM7 5h8v4H7V5Zm12 14H5V5h1v6h10V9h3v10Zm-7-7a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/>',
    "delete": '<path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12Zm3.5-9h1.5v8H9.5v-8Zm3.5 0h1.5v8H13v-8ZM15.5 4l-1-1h-5l-1 1H5v2h14V4h-3.5Z"/>',
    "edit": '<path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25Zm17.71-10.04a1.003 1.003 0 0 0 0-1.42l-2.5-2.5a1.003 1.003 0 0 0-1.42 0l-1.96 1.96 3.75 3.75 2.13-1.79Z"/>',
    "search": '<path d="M9.5 3a6.5 6.5 0 1 0 3.98 11.64L19.85 21 21 19.85l-6.36-6.37A6.5 6.5 0 0 0 9.5 3Zm0 2a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Z"/>',
    "refresh": '<path d="M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.75 10h-2.1A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h8V3l-3.35 3.35Z"/>',
    "copy": '<path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1Zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2Zm0 16H8V7h11v14Z"/>',
    "calendar": '<path d="M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2Zm0 15H5V9h14v10ZM5 7V6h14v1H5Z"/>',
    "warning": '<path d="M1 21h22L12 2 1 21Zm12-3h-2v-2h2v2Zm0-4h-2v-4h2v4Z"/>',
    "check": '<path d="m9 16.17-4.17-4.17L3.41 13.41 9 19 21 7l-1.41-1.41L9 16.17Z"/>',
    "money": '<path d="M12 1a11 11 0 1 0 0 22 11 11 0 0 0 0-22Zm1 17.93V20h-2v-1.11c-1.72-.37-3-1.91-3-3.74h2c0 1.1.9 2 2 2s2-.55 2-1.5c0-.91-.73-1.23-2.35-1.68C9.87 13.47 8 12.73 8 10.25c0-1.69 1.17-3.13 3-3.56V5h2v1.69c1.72.37 3 1.91 3 3.74h-2c0-1.1-.9-2-2-2s-2 .55-2 1.5c0 .91.73 1.23 2.35 1.68 1.78.5 3.65 1.24 3.65 3.72 0 1.69-1.17 3.17-3 3.6Z"/>',
}


def _svg(icon_name: str, color: str) -> bytes:
    path = _PATHS.get(icon_name, _PATHS["dashboard"])
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="24" height="24" fill="{color}">{path}</svg>'
    ).encode("utf-8")


@lru_cache(maxsize=256)
def icon(icon_name: str, color: str = "#52647a", size: int = 20) -> QIcon:
    renderer = QSvgRenderer(QByteArray(_svg(icon_name, color)))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def tinted_icon(icon_name: str, color: QColor | str, size: int = 20) -> QIcon:
    return icon(icon_name, QColor(color).name(), size)
