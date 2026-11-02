"""Optional sample identification and free-text notes for metadata only."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class SampleNotes(QWidget):
    def __init__(self, config):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.toggle = QToolButton()
        self.toggle.setText("Sample && notes")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setCheckable(True)
        self.toggle.setToolTip("Optional sample label and notes saved in metadata only")
        layout.addWidget(self.toggle)
        self.body = QWidget()
        form = QFormLayout(self.body)
        form.setContentsMargins(0, 4, 0, 4)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.sample_label = QLineEdit(config.sample_label)
        self.sample_label.setAccessibleName("Sample label")
        self.sample_label.setPlaceholderText("Sample or device identifier (optional)")
        self.experiment_notes = QPlainTextEdit()
        self.experiment_notes.setPlainText(config.experiment_notes)
        self.experiment_notes.setAccessibleName("Experiment notes")
        self.experiment_notes.setPlaceholderText(
            "Preparation, special conditions, description… (optional)"
        )
        self.experiment_notes.setMaximumHeight(100)
        form.addRow("Sample label", self.sample_label)
        form.addRow("Experiment notes", self.experiment_notes)
        layout.addWidget(self.body)
        self.body.hide()
        self.toggle.toggled.connect(self.set_expanded)

    def set_expanded(self, expanded):
        self.body.setVisible(expanded)
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def set_running(self, running):
        self.sample_label.setReadOnly(running)
        self.experiment_notes.setReadOnly(running)

    def values(self):
        return {
            "sample_label": self.sample_label.text(),
            "experiment_notes": self.experiment_notes.toPlainText(),
        }
