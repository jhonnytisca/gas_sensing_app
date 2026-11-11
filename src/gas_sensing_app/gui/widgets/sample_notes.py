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
        self.toggle.setText("Experiment")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setCheckable(True)
        self.toggle.setToolTip(
            "Sample, devices and experiment details used to organize results"
        )
        layout.addWidget(self.toggle)
        self.body = QWidget()
        form = QFormLayout(self.body)
        form.setContentsMargins(0, 4, 0, 4)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.sample_name = QLineEdit(config.sample_name or config.sample_label)
        self.device = QLineEdit(config.device)
        self.device.setPlaceholderText("102, 102-105, 102,103,106…")
        self.experiment_name = QLineEdit(config.experiment_name)
        self.experiment_name.setPlaceholderText("NO2, NH3, cleaning, baseline…")
        self.description = QPlainTextEdit()
        self.description.setPlainText(config.description or config.experiment_notes)
        self.description.setMaximumHeight(100)
        self.description.setPlaceholderText("Preparation, conditions and observations")
        for label, widget in (
            ("Sample name", self.sample_name),
            ("Device", self.device),
            ("Experiment name", self.experiment_name),
            ("Description", self.description),
        ):
            widget.setAccessibleName(label)
            form.addRow(label, widget)
        # Compatibility for callers using the former annotation widgets.
        self.sample_label = self.sample_name
        self.experiment_notes = self.description
        layout.addWidget(self.body)
        self.toggle.setChecked(True)
        self.set_expanded(True)
        self.toggle.toggled.connect(self.set_expanded)

    def set_expanded(self, expanded):
        self.body.setVisible(expanded)
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def set_running(self, running):
        for widget in (
            self.sample_name,
            self.device,
            self.experiment_name,
            self.description,
        ):
            widget.setReadOnly(running)

    def values(self):
        return {
            "sample_name": self.sample_name.text(),
            "device": self.device.text(),
            "experiment_name": self.experiment_name.text(),
            "description": self.description.toPlainText(),
        }
