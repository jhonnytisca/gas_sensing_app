"""Independent, read-only results browser. File parsing runs off the GUI thread."""

import json
from html import escape
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from pyqtgraph.exporters import ImageExporter

from gas_sensing_app.gui.styles.theme_manager import (
    get_pyqtgraph_config,
    load_theme,
)
from gas_sensing_app.gui.widgets.legend import ThickLineSample
from gas_sensing_app.gui.widgets.theme_selector import ThemeSelector
from gas_sensing_app.results import (
    ELECTRICAL,
    display_bounds,
    list_csv_files,
    load_result,
    merge_files,
)

COLORS = [
    "#49a8ee",
    "#f09545",
    "#43b99b",
    "#d982bc",
    "#a99af0",
    "#c0b55b",
    "#e66f76",
    "#8da9b7",
]


class LoadSignals(QObject):
    finished = pyqtSignal(int, object, str)


class LoadFile(QRunnable):
    def __init__(self, token, path):
        super().__init__()
        self.token, self.path = token, path
        self.signals = LoadSignals()

    def run(self):
        try:
            result, error = load_result(self.path), ""
        except Exception as exc:
            result, error = None, str(exc)
        self.signals.finished.emit(self.token, result, error)


class ResultsPreviewer(QMainWindow):
    def __init__(self, default_folder):
        super().__init__()
        self.default_folder = Path(default_folder).resolve()
        self.paths = []
        self.result = None
        self.load_token = 0
        self.curves = {}
        self.plots = {}
        self.export_note = None
        self.divisors = {}
        self.busy = False
        self.setWindowTitle("Gas Sensing · Results previewer")
        self.resize(1350, 900)
        self.setMinimumSize(850, 600)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        header = QHBoxLayout()
        title = QLabel("Results previewer")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self.metadata_button = QPushButton("Session details")
        self.metadata_button.clicked.connect(self.show_metadata)
        header.addWidget(self.metadata_button)
        self.export_button = QPushButton("Export PNG")
        self.export_button.clicked.connect(self.choose_export)
        header.addWidget(self.export_button)
        self.theme_selector = ThemeSelector()
        self.theme_selector.currentIndexChanged.connect(self.change_theme)
        header.addWidget(self.theme_selector)
        layout.addLayout(header)
        split = QSplitter()
        layout.addWidget(split, 1)
        side = QWidget()
        sidebar = QVBoxLayout(side)
        sidebar.setContentsMargins(0, 0, 8, 0)
        self.list_mode = QComboBox()
        self.list_mode.addItems(["Replace displayed files", "Add to displayed files"])
        self.list_mode.setToolTip("Changes only this list, never files on disk.")
        sidebar.addWidget(self.list_mode)
        row = QHBoxLayout()
        for title, action in (
            ("Open folder…", self.choose_folder),
            ("Open files…", self.choose_files),
        ):
            button = QPushButton(title)
            button.clicked.connect(action)
            row.addWidget(button)
        sidebar.addLayout(row)
        self.recursive = QCheckBox("Include subfolders")
        sidebar.addWidget(self.recursive)
        self.folder_label = QLabel(str(self.default_folder))
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        sidebar.addWidget(self.folder_label)
        self.files = QListWidget()
        self.files.currentRowChanged.connect(self.select_file)
        sidebar.addWidget(self.files, 2)
        row = QHBoxLayout()
        for title, action in (
            ("Default folder", self.open_default),
            ("Reload file", self.reload_file),
        ):
            button = QPushButton(title)
            button.clicked.connect(action)
            row.addWidget(button)
        sidebar.addLayout(row)
        sensors_heading = QHBoxLayout()
        sensors_heading.addWidget(QLabel("Sensors"), 1)
        for title, checked in (("All", True), ("None", False)):
            button = QToolButton()
            button.setText(title)
            button.clicked.connect(
                lambda _, checked=checked: self.check_sensors(checked)
            )
            sensors_heading.addWidget(button)
        sidebar.addLayout(sensors_heading)
        self.sensors = QListWidget()
        self.sensors.setMaximumHeight(170)
        self.sensors.itemChanged.connect(self.redraw)
        sidebar.addWidget(self.sensors)
        sidebar.addWidget(QLabel("Gas channels"))
        self.gases = QListWidget()
        self.gases.setMaximumHeight(125)
        self.gases.itemChanged.connect(self.redraw)
        sidebar.addWidget(self.gases)
        self.correction = QCheckBox("Legacy flow correction (preview only)")
        self.correction.setToolTip(
            "Off by default. Divide reported flows only; setpoints stay unchanged. "
            "Do not enable for files already saved without extra scaling."
        )
        self.correction.toggled.connect(self.correction_changed)
        sidebar.addWidget(self.correction)
        self.divisor_panel = QWidget()
        self.divisor_form = QFormLayout(self.divisor_panel)
        self.divisor_form.setContentsMargins(0, 0, 0, 0)
        self.divisor_panel.hide()
        sidebar.addWidget(self.divisor_panel)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(side)
        scroll.setMinimumWidth(280)
        split.addWidget(scroll)
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(8, 0, 0, 0)
        self.file_title = QLabel("Select a measurement")
        self.file_title.setProperty("role", "compactInfo")
        self.file_title.setWordWrap(True)
        main.addWidget(self.file_title)
        controls = QHBoxLayout()
        group = QFrame()
        group.setObjectName("plotSelector")
        buttons = QHBoxLayout(group)
        buttons.setContentsMargins(3, 3, 3, 3)
        self.signal_buttons = {}
        for key, label in (
            ("resistance_ohm", "R"),
            ("voltage_V", "V"),
            ("current_A", "I"),
            ("flows", "Flow"),
        ):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(True)
            button.setToolTip(ELECTRICAL[key][0] if key in ELECTRICAL else "Gas flows")
            button.toggled.connect(self.redraw)
            self.signal_buttons[key] = button
            buttons.addWidget(button)
        controls.addWidget(group)
        self.setpoints = QCheckBox("Setpoints")
        self.reported = QCheckBox("Reported flows")
        for widget in (self.setpoints, self.reported):
            widget.setChecked(True)
            widget.toggled.connect(self.redraw)
            controls.addWidget(widget)
        controls.addStretch()
        main.addLayout(controls)
        views = QHBoxLayout()
        self.robust = QCheckBox("Spike-resistant view")
        self.robust.setChecked(True)
        self.robust.setToolTip(
            "Fits Y axes to each curve's 1st–99th percentiles in the visible time "
            "window. No points are removed. Setpoints retain their full range."
        )
        self.robust.toggled.connect(self.fit_y)
        views.addWidget(self.robust)
        for title, action in (
            ("Fit view", self.fit_view),
            ("Full view", self.full_view),
        ):
            button = QPushButton(title)
            button.clicked.connect(action)
            views.addWidget(button)
        views.addStretch()
        main.addLayout(views)
        self.canvas = pg.GraphicsLayoutWidget()
        main.addWidget(self.canvas, 1)
        self.view_note = QLabel(
            "Wheel to zoom · drag to pan · right-click for axis controls"
        )
        self.view_note.setWordWrap(True)
        self.view_note.hide()
        self.status = QLabel("Read-only preview · no instrument connections")
        self.status.setWordWrap(True)
        self.status.setProperty("role", "compactInfo")
        main.addWidget(self.status)
        split.addWidget(content)
        split.setSizes([320, 1000])
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.setInterval(150)
        self.fit_timer.timeout.connect(self.fit_y)
        self.change_theme()
        self.open_default()

    def open_default(self):
        self.open_folder(self.default_folder, replace=True)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select results folder", str(self.default_folder)
        )
        if folder:
            self.open_folder(folder, replace=self.list_mode.currentIndex() == 0)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select measurements",
            str(self.default_folder),
            "Experiment CSV (*.csv *.CSV)",
        )
        if files:
            self.set_files(files, replace=self.list_mode.currentIndex() == 0)
            self.folder_label.setText("Selected files · paths shown in tooltips")

    def open_folder(self, folder, replace=True):
        try:
            paths = list_csv_files(folder, self.recursive.isChecked())
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))
            return
        self.set_files(paths, replace)
        self.folder_label.setText(
            str(Path(folder).resolve())
            if replace
            else "Multiple sources · paths shown in tooltips"
        )

    def set_files(self, paths, replace=True):
        old = (
            self.paths[self.files.currentRow()]
            if self.files.currentRow() >= 0
            else None
        )
        self.paths = merge_files(self.paths, paths, replace)
        self.files.blockSignals(True)
        self.files.clear()
        for path in self.paths:
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            self.files.addItem(item)
        self.files.blockSignals(False)
        if self.paths:
            index = self.paths.index(old) if not replace and old in self.paths else 0
            self.files.setCurrentRow(index)
        else:
            self.select_file(-1)
            self.status.setText("No CSV files in this selection.")

    def reload_file(self):
        self.select_file(self.files.currentRow())

    def select_file(self, index):
        self.load_token += 1
        self.result = None
        self.busy = True
        self.sensors.clear()
        self.gases.clear()
        self.correction.setChecked(False)
        self.busy = False
        self.canvas.clear()
        self.export_note = None
        self.plots.clear()
        self.curves.clear()
        self.export_button.setEnabled(False)
        self.metadata_button.setEnabled(False)
        if index < 0:
            self.file_title.setText("Select a measurement")
            return
        path = self.paths[index]
        self.file_title.setText(path.name)
        self.file_title.setToolTip(str(path))
        self.status.setText(
            "Loading snapshot… Acquisition in the other window continues independently."
        )
        job = LoadFile(self.load_token, path)
        job.signals.finished.connect(self.loaded)
        QThreadPool.globalInstance().start(job)

    def loaded(self, token, result, error):
        if token != self.load_token:
            return
        if error:
            self.status.setText(f"Cannot preview this file: {error}")
            return
        self.result = result
        self.busy = True
        for sensor in result.sensor_ids:
            mask = result.sensors == sensor
            valid = any(
                np.isfinite(result.values[k][mask]).any()
                for k in ELECTRICAL
                if k in result.values
            )
            item = QListWidgetItem(
                sensor if valid else f"{sensor} — no valid electrical readings"
            )
            item.setData(Qt.ItemDataRole.UserRole, sensor)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.sensors.addItem(item)
        while self.divisor_form.rowCount():
            self.divisor_form.removeRow(0)
        self.divisors.clear()
        for channel, gas in sorted(result.gases.items()):
            item = QListWidgetItem(f"CH{channel} · {gas['name']}")
            item.setData(Qt.ItemDataRole.UserRole, channel)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.gases.addItem(item)
            divisor = QDoubleSpinBox()
            divisor.setDecimals(4)
            divisor.setRange(0.0001, 1000000)
            divisor.setValue(result.flow_divisors()[channel])
            divisor.valueChanged.connect(self.redraw)
            self.divisors[channel] = divisor
            self.divisor_form.addRow(f"CH{channel} reported ÷", divisor)
        for key, button in self.signal_buttons.items():
            available = (
                bool(result.gases)
                if key == "flows"
                else key in result.values and np.isfinite(result.values[key]).any()
            )
            button.setEnabled(bool(available))
        self.correction.setEnabled(bool(result.gases))
        self.busy = False
        self.metadata_button.setEnabled(True)
        self.robust.setChecked(True)
        self.redraw()

    @staticmethod
    def checked_items(widget):
        return [
            widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(widget.count())
            if widget.item(i).checkState() == Qt.CheckState.Checked
        ]

    def check_sensors(self, checked):
        self.busy = True
        for index in range(self.sensors.count()):
            self.sensors.item(index).setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
        self.busy = False
        self.redraw()

    def correction_changed(self):
        self.divisor_panel.setVisible(self.correction.isChecked())
        self.redraw()

    def redraw(self, *_):
        if self.busy or self.result is None:
            return
        self.fit_timer.stop()
        self.canvas.clear()
        self.plots.clear()
        self.curves.clear()
        result = self.result
        sensors = self.checked_items(self.sensors)
        sensor_mask = np.isin(result.sensors, sensors)
        time_min = result.time_s / 60
        self.export_note = self.canvas.addLabel(
            "", row=0, col=0, color=self.foreground, size="8pt"
        )
        for key, button in self.signal_buttons.items():
            if not (button.isChecked() and button.isEnabled()):
                continue
            title, unit = ELECTRICAL.get(key, ("Gas flows", "sccm"))
            plot = self.canvas.addPlot(row=1 + len(self.plots), col=0)
            plot.setTitle(title, size="10pt")
            plot.setLabel("left", title, units=unit)
            plot.getAxis("left").setWidth(85)
            plot.setLabel("bottom", "Elapsed time", units="min")
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.addLegend(colCount=2, labelTextSize="8pt", sampleType=ThickLineSample)
            plot.setClipToView(True)
            plot.setDownsampling(auto=True, mode="peak")
            plot.setMenuEnabled(True)
            plot.setMouseEnabled(x=True, y=True)
            self.plots[key] = plot
            self.curves[key] = []
            if key in ELECTRICAL:
                for index, sensor in enumerate(result.sensor_ids):
                    if sensor in sensors:
                        mask = result.sensors == sensor
                        self.add_curve(
                            key,
                            time_min[mask],
                            result.values[key][mask],
                            sensor,
                            COLORS[index % len(COLORS)],
                        )
            else:
                self.add_flow_curves(time_min, sensor_mask)
        plots = list(self.plots.values())
        if plots:
            for plot in plots[:-1]:
                plot.setXLink(plots[-1])
            plots[-1].sigXRangeChanged.connect(self.schedule_fit)
        self.export_button.setEnabled(bool(plots))
        self.fit_view()
        self.summary()

    def add_flow_curves(self, time_min, sensor_mask):
        for index, (ch, gas) in enumerate(sorted(self.result.gases.items())):
            if ch not in self.checked_items(self.gases):
                continue
            color = COLORS[index % len(COLORS)]
            for kind, control in (
                ("setpoint", self.setpoints),
                ("actual", self.reported),
            ):
                if kind not in gas or not control.isChecked():
                    continue
                values = self.result.values[gas[kind]][sensor_mask]
                if kind == "actual" and self.correction.isChecked():
                    values = values / self.divisors[ch].value()
                label = "set" if kind == "setpoint" else "reported"
                self.add_curve(
                    "flows",
                    time_min[sensor_mask],
                    values,
                    f"CH{ch} {gas['name']} · {label}",
                    color,
                    kind == "setpoint",
                )

    def add_curve(self, key, x, y, name, color, setpoint=False):
        if not np.isfinite(y).any():
            return
        pen = pg.mkPen(
            color,
            width=1.7,
            style=Qt.PenStyle.DashLine if setpoint else Qt.PenStyle.SolidLine,
        )
        self.plots[key].plot(x, y, pen=pen, name=name, connect="finite")
        self.curves[key].append((x, y, setpoint))

    def schedule_fit(self, *_):
        if self.robust.isChecked():
            self.fit_timer.start()

    def fit_view(self):
        if self.result is None or not len(self.result.time_s):
            return
        for plot in self.plots.values():
            plot.setXRange(
                self.result.time_s[0] / 60,
                max(self.result.time_s[-1] / 60, self.result.time_s[0] / 60 + 0.01),
                padding=0.01,
            )
        self.fit_y()

    def full_view(self):
        self.robust.setChecked(False)
        self.fit_view()

    def fit_y(self, *_):
        if self.result is None:
            return
        outside = 0
        for key, plot in self.plots.items():
            xmin, xmax = plot.viewRange()[0]
            series = [
                (y[(x >= xmin) & (x <= xmax)], keep) for x, y, keep in self.curves[key]
            ]
            bounds = display_bounds(series, self.robust.isChecked())
            if bounds:
                lo, hi, count = bounds
                plot.setYRange(lo, hi, padding=0)
                outside += count
        mode = "Spike-resistant axes" if self.robust.isChecked() else "Full-range axes"
        self.view_note.setText(
            f"{mode} · {outside} plotted values outside Y view · no samples removed. "
            "Wheel: zoom; drag: pan."
        )
        if self.export_note is not None:
            correction = "Correction OFF"
            if self.correction.isChecked():
                correction = "Flow correction: " + ", ".join(
                    f"CH{ch}÷{spin.value():g}"
                    for ch, spin in self.divisors.items()
                    if ch in self.checked_items(self.gases)
                )
            self.plot_note = f"{correction} · {mode} · {outside} off-scale"
            self.export_note.setText(
                self.plot_note,
                color=self.foreground,
                size="8pt",
            )
            self.canvas.setToolTip(self.view_note.text())
        self.summary()

    def summary(self):
        result = self.result
        scans = f" · {len(result.scan_ids)} scan IDs" if result.scan_ids else ""
        self.status.setText(
            f"{len(result.time_s):,} rows · "
            f"{len(self.checked_items(self.sensors))}/{len(result.sensor_ids)} sensors"
            f"{scans} · Read-only"
            + (f" · {len(result.warnings)} notices (hover)" if result.warnings else "")
        )
        self.status.setToolTip(
            "\n".join(result.warnings) or "Reload file to update the snapshot."
        )

    def change_theme(self):
        theme = self.theme_selector.currentData()
        self.setStyleSheet(load_theme(theme))
        colors = get_pyqtgraph_config(theme)
        self.foreground = colors["foreground"]
        self.canvas.setBackground(colors["background"])
        self.redraw()

    def show_metadata(self):
        if self.result is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Session details")
        dialog.resize(760, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        content = (
            json.dumps(self.result.metadata, indent=2, ensure_ascii=False)
            if self.result.metadata is not None
            else "No matching metadata file available."
        )
        text.setPlainText(f"CSV: {self.result.path}\n\n{content}")
        layout.addWidget(text)
        dialog.exec()

    def choose_export(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export current plot view",
            str(self.result.path.with_suffix(".png")),
            "PNG image (*.png)",
        )
        if path:
            try:
                self.export_png(Path(path).with_suffix(".png"))
            except Exception as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def export_png(self, path):
        # Include the filename in exports without duplicating it above live plots.
        if self.export_note is not None:
            self.export_note.setText(
                f"{escape(self.result.path.name)}<br>{self.plot_note}", size="8pt"
            )
        try:
            exporter = ImageExporter(self.canvas.scene())
            exporter.parameters()["width"] = 1800
            exporter.export(str(path))
        finally:
            if self.export_note is not None:
                self.export_note.setText(self.plot_note, size="8pt")

    def closeEvent(self, event):
        self.load_token += 1
        self.fit_timer.stop()
        super().closeEvent(event)
