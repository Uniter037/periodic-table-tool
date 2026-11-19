"""Small vector command icons, rendered at multiple device-pixel ratios."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_DRAWINGS = {
    'heatmap': ''.join(f'<rect x="{x}" y="{y}" width="5" height="5" rx=".7" fill="{color}" stroke="none"/>'
                       for y in (3, 10, 17) for x, color in ((3, '#087f78'), (10, '#58aaa4'), (17, '#b4dad7'))),
    'labels': '<path d="M3 20 10 4l7 16M5.5 14h9M18 10h5m-2.5 0v10"/>',
    'settings': '<path d="M3 6h18M3 12h18M3 18h18"/><rect x="7" y="3" width="4" height="6" rx="1" fill="white"/><rect x="14" y="9" width="4" height="6" rx="1" fill="white"/><rect x="5" y="15" width="4" height="6" rx="1" fill="white"/>',
    'range': '<path d="M4 5v14h16M5 16 10 11l4 3 6-9M16 5h4v4"/>',
    'colorbar': '<rect x="6" y="3" width="7" height="18" rx="1" fill="url(#color)" stroke="none"/><path d="M16 4h4M16 12h4M16 20h4"/>',
    'ticks': '<path d="M5 3v18M5 4h4M5 12h4M5 20h4M13 4h7M13 12h7M13 20h7"/>',
    'edit': '<path d="m4 16-1 5 5-1L21 7l-4-4ZM14 6l4 4"/>',
    'save': '<path d="M4 3h14l3 3v15H3V3ZM7 3v7h10V3M7 21v-7h10v7"/>',
    'undo': '<path d="m9 4-6 6 6 6M4 10h10a7 7 0 0 1 7 7v3"/>',
    'redo': '<path d="m15 4 6 6-6 6M20 10h-10a7 7 0 0 0-7 7v3"/>',
    'export': '<path d="M5 14v7h14v-7M12 3v13M7 8l5-5 5 5"/>',
    'import': '<path d="M5 14v7h14v-7M12 3v13M7 11l5 5 5-5"/>',
    'preset': '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="8" r="1"/><circle cx="15" cy="7" r="1"/><circle cx="18" cy="13" r="1"/><path d="M12 21v-4h-4v-4H3"/>',
    'batch': '<path d="M7 3h14v14M3 7h14v14H3ZM3 12h14M8 7v14"/>',
}


def command_icon(name):
    drawing = _DRAWINGS.get(name)
    if drawing is None:
        return None
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           '<defs><linearGradient id="color" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#d75b50"/><stop offset=".5" stop-color="#f5f4ef"/><stop offset="1" stop-color="#4673ba"/></linearGradient></defs>'
           '<g stroke="#42616b" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round">' + drawing + '</g></svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    icon = QIcon()
    for ratio in (1, 2, 3):
        pixmap = QPixmap(24 * ratio, 24 * ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(ratio)
        icon.addPixmap(pixmap)
    return icon
