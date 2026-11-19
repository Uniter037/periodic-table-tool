"""Shared visual tokens; application geometry stays in logical Qt pixels."""
import os
from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase


def apply_theme(application, scale=1.0):
    # Windows' offscreen plugin does not enumerate system fonts. Load installed
    # fonts for deterministic headless UI QA; the native desktop needs no copy.
    if not QFontDatabase.families() and os.name == 'nt':
        directory = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('msyh.ttc', 'segoeui.ttf'):
            if (directory / name).is_file():
                QFontDatabase.addApplicationFont(str(directory / name))
    font = QFont('Microsoft YaHei UI')
    font.setPointSizeF(9.5 * float(scale))
    application.setFont(font)
    application.setStyle('Fusion')
    application.setStyleSheet('''
        QWidget { color: #243746; }
        QWidget#RibbonPage { background: #ffffff; }
        QWidget#RibbonGroup { border-right: 1px solid #dbe4eb; }
        QMainWindow, QDialog { background: #f3f6f9; }
        QLabel#Brand { font-weight: 700; font-size: 18px; color: #087f78; }
        QLabel#Heading { font-weight: 600; padding: 5px 0; }
        QLabel#Muted { color: #607383; }
        QLabel#Error { color: #b13c29; }
        QToolBar { border: 0; background: #ffffff; spacing: 5px; padding: 5px; }
        QToolButton { border: 1px solid transparent; border-radius: 5px; padding: 6px; }
        QToolButton:hover { background: #e4f2f0; border-color: #b4d9d6; }
        QToolButton:checked { background: #d5eeeb; color: #066c66; }
        QPushButton { background: #ffffff; border: 1px solid #cdd7df; border-radius: 5px; padding: 6px 12px; }
        QPushButton:hover { border-color: #087f78; background: #edf7f6; }
        QPushButton:disabled { color: #a0aab2; background: #f2f4f6; }
        QPushButton#Primary { background: #087f78; border: 1px solid #087f78; color: white; font-weight: 600; }
        QPushButton#Primary:hover { background: #066c66; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
            background: #ffffff; border: 1px solid #cad5df; border-radius: 4px; padding: 5px;
            selection-background-color: #b9e5df; selection-color: #183a37;
        }
        QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #087f78; }
        QLineEdit[invalid="true"] { border: 1px solid #bd4632; background: #fff5f2; }
        QTabWidget::pane { border: 1px solid #d7e0e7; background: #ffffff; border-radius: 4px; }
        QTabBar::tab { padding: 8px 16px; color: #4f6070; background: #eef3f7; border-bottom: 2px solid transparent; }
        QTabBar::tab:selected { background: #ffffff; color: #087f78; border-bottom: 2px solid #087f78; font-weight: 600; }
        QDockWidget { font-weight: 600; }
        QDockWidget::title { background: #eaf0f5; padding: 8px; border-bottom: 1px solid #d8e2ea; }
        QTreeWidget, QTableView, QListWidget { background: #ffffff; alternate-background-color: #f5f8fb; border: 1px solid #d8e2ea; gridline-color: #e3e9ee; selection-background-color: #d5eeeb; selection-color: #174e49; }
        QHeaderView::section { background: #eaf0f5; color: #4c6070; border: 0; border-right: 1px solid #d5dfe6; border-bottom: 1px solid #d5dfe6; padding: 6px; }
        QTreeWidget::item { padding: 6px 2px; }
        QGroupBox { border: 1px solid #dbe3e9; border-radius: 5px; margin-top: 12px; padding-top: 8px; }
        QGroupBox::title { subcontrol-origin: margin; padding: 0 5px; color: #536a79; }
        QStatusBar { background: #ffffff; border-top: 1px solid #d7e0e7; }
        QSplitter::handle { background: #e6edf3; }
        QSplitter::handle:hover { background: #b8dcd8; }
        QScrollArea { border: 0; background: #ffffff; }
        QMenu { background: #ffffff; border: 1px solid #cbd6df; padding: 4px; }
        QMenu::item { padding: 7px 24px; }
        QMenu::item:selected { background: #e0f1ee; }
        QToolTip { background: #ffffff; color: #243746; border: 1px solid #cbd6df; padding: 5px; }
    ''')
