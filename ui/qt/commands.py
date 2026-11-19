"""One command registry supplies ribbon, menu, shortcuts and command search."""
from dataclasses import dataclass
from collections import OrderedDict
from PySide6.QtCore import QObject, Qt, Signal, QSize
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QDialogButtonBox,
    QTabWidget, QWidget, QHBoxLayout, QScrollArea, QToolButton, QLabel,
)


@dataclass(frozen=True)
class Command:
    id: str
    label: str
    tab: str
    group: str
    shortcut: str = ''
    keywords: str = ''
    checkable: bool = False


class CommandRegistry(QObject):
    registered = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window, self.commands, self.actions = window, OrderedDict(), {}

    def register(self, command, callback, icon=None):
        if command.id in self.actions:
            raise ValueError('Duplicate command: ' + command.id)
        action = QAction(command.label, self.window)
        action.setObjectName(command.id)
        action.setCheckable(command.checkable)
        if icon is not None:
            action.setIcon(icon)
        if command.shortcut:
            action.setShortcut(QKeySequence(command.shortcut))
        action.setToolTip(f'{command.tab} → {command.group} → {command.label}' +
                          (f' ({command.shortcut})' if command.shortcut else ''))
        action.triggered.connect(callback)
        self.window.addAction(action)
        self.commands[command.id], self.actions[command.id] = command, action
        self.registered.emit(command.id)
        return action

    def search(self, query):
        tokens = query.casefold().split()
        return [command for command in self.commands.values()
                if all(token in ' '.join((command.id, command.label, command.tab,
                                          command.group, command.keywords)).casefold()
                       for token in tokens)]

    def palette(self, initial=''):
        dialog = QDialog(self.window)
        dialog.setWindowTitle('搜索功能')
        dialog.resize(620, 440)
        layout = QVBoxLayout(dialog)
        search, results = QLineEdit(), QListWidget()
        search.setPlaceholderText('输入功能、分类或快捷键关键词…')
        layout.addWidget(search)
        layout.addWidget(results)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        def refresh(query):
            results.clear()
            for command in self.search(query):
                results.addItem(f'{command.label}    {command.tab} / {command.group}    {command.shortcut}')
                item = results.item(results.count() - 1)
                item.setData(Qt.ItemDataRole.UserRole, command.id)
                if not self.actions[command.id].isEnabled():
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            results.setCurrentRow(0)
        def execute():
            item = results.currentItem()
            if item and self.actions[item.data(Qt.ItemDataRole.UserRole)].isEnabled():
                dialog.accept()
                self.actions[item.data(Qt.ItemDataRole.UserRole)].trigger()
        search.textChanged.connect(refresh)
        search.returnPressed.connect(execute)
        results.itemActivated.connect(lambda _: execute())
        refresh(initial)
        search.setText(initial)
        search.setFocus()
        dialog.exec()


class Ribbon(QTabWidget):
    """Each category scrolls horizontally on narrow windows instead of clipping."""
    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.setDocumentMode(True)
        self.setMaximumHeight(145)
        self.setMinimumHeight(128)
        self.rebuild()
        registry.registered.connect(lambda _: self.rebuild())

    def rebuild(self):
        selected = self.tabText(self.currentIndex())
        while self.count():
            widget = self.widget(0)
            self.removeTab(0)
            widget.deleteLater()
        groups = OrderedDict()
        for command in self.registry.commands.values():
            groups.setdefault(command.tab, OrderedDict()).setdefault(command.group, []).append(command)
        for tab, categories in groups.items():
            scroll, page = QScrollArea(), QWidget()
            page.setObjectName('RibbonPage')
            scroll.setWidgetResizable(True)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            layout = QHBoxLayout(page)
            layout.setContentsMargins(8, 4, 8, 4)
            for title, commands in categories.items():
                group = QWidget()
                group.setObjectName('RibbonGroup')
                column = QVBoxLayout(group)
                column.setContentsMargins(6, 0, 12, 0)
                row = QHBoxLayout()
                for command in commands:
                    button = QToolButton()
                    button.setDefaultAction(self.registry.actions[command.id])
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    button.setMinimumWidth(68)
                    button.setIconSize(QSize(24, 24))
                    row.addWidget(button)
                column.addLayout(row)
                label = QLabel(title)
                label.setObjectName('Muted')
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                column.addWidget(label)
                layout.addWidget(group)
            layout.addStretch()
            scroll.setWidget(page)
            self.addTab(scroll, tab)
        if selected in groups:
            self.setCurrentIndex(list(groups).index(selected))
