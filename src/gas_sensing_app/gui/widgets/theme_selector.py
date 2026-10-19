"""Keyboard-accessible, explicit dark/light appearance selection."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton

from gas_sensing_app.gui.styles.theme_manager import Theme


class ThemeSelector(QFrame):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("themeSelector")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.group = QButtonGroup(self)
        self.themes = [Theme.DARK, Theme.LIGHT]
        for index, theme in enumerate(self.themes):
            button = QPushButton(theme.value.title())
            button.setCheckable(True)
            button.setAccessibleName(f"Use {theme.value} theme")
            button.setToolTip(
                f"Switch the interface and all plots to {theme.value} mode"
            )
            self.group.addButton(button, index)
            layout.addWidget(button)
        self.group.button(0).setChecked(True)
        self.group.idClicked.connect(self.currentIndexChanged)

    def currentData(self):
        return self.themes[self.group.checkedId()]

    def setCurrentIndex(self, index):
        if index != self.group.checkedId():
            self.group.button(index).setChecked(True)
            self.currentIndexChanged.emit(index)
