"""Operator workspace: guided setup, persistent actions, and live monitoring."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gas_sensing_app.gui.styles.theme_manager import DEFAULT_THEME, load_theme

from .widgets.plots import MeasurementPlots
from .widgets.setup_panel import SetupPanel, hint
from .widgets.theme_selector import ThemeSelector


class Dashboard(QMainWindow):
    close_requested = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = False
        self.setWindowTitle("Gas Sensing · Experiment workspace")
        self.setStyleSheet(load_theme(DEFAULT_THEME))
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1440, screen.width()), min(960, screen.height()))
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        self.outer = outer
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(12)
        outer.addWidget(self.build_header())
        self.status_label = QLabel("Ready to prepare a measurement")
        self.status_label.setObjectName("statusBanner")
        self.status_label.setProperty("state", "ready")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        self.compact_nav = QTabBar()
        self.compact_nav.addTab("Prepare experiment")
        self.compact_nav.addTab("Live readings")
        self.compact_nav.hide()
        self.compact_nav.currentChanged.connect(self.select_compact_view)
        outer.addWidget(self.compact_nav)
        self.splitter = QSplitter()
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)
        self.setup_view = self.build_setup()
        self.monitor_view = self.build_monitor()
        self.splitter.addWidget(self.setup_view)
        self.splitter.addWidget(self.monitor_view)
        self.splitter.setSizes([440, 960])
        outer.addWidget(self.actions)
        outer.addWidget(self.build_details())
        self.setup.changed.connect(self.refresh_summary)
        self.setup.changed.connect(self.update_plot_availability)
        self.update_plot_availability()
        self.refresh_summary()

    def update_plot_availability(self):
        self.plots.set_measurement(
            self.setup.instrument.currentData(),
            self.setup.measurement_mode.currentData(),
        )

    def build_header(self):
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Gas Sensing")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        mode = QLabel(
            "SIMULATION" if self.config.hardware.use_mock else "REAL INSTRUMENTS"
        )
        mode.setObjectName("modeBadge")
        mode.setToolTip(
            "Mock devices · no physical outputs"
            if self.config.hardware.use_mock
            else "This session controls connected laboratory instruments"
        )
        layout.addWidget(mode)
        layout.addStretch()
        self.theme_selector = ThemeSelector()
        layout.addWidget(self.theme_selector)
        return header

    def build_setup(self):
        panel = QFrame()
        panel.setObjectName("setupPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 12, 12)
        title = QLabel("Prepare your measurement")
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)
        self.setup = SetupPanel(self.config)
        layout.addWidget(self.setup, 1)
        self.summary = hint("")
        self.summary.setObjectName("runSummary")
        self.actions = QFrame()
        self.actions.setObjectName("actionBar")
        actions_layout = QVBoxLayout(self.actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)
        actions_layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.start_manual_btn = QPushButton("Start measurement")
        self.start_recipe_btn = QPushButton("Start recipe")
        self.start_recipe_btn.setEnabled(False)
        self.start_recipe_btn.hide()
        for button in (self.start_manual_btn, self.start_recipe_btn):
            button.setProperty("role", "primary")
            button.setMinimumHeight(40)
            buttons.addWidget(button)
        self.apply_manual_btn = QPushButton("Apply new gas flows")
        self.apply_manual_btn.setEnabled(False)
        self.apply_manual_btn.hide()
        buttons.addWidget(self.apply_manual_btn)
        self.stop_btn = QPushButton("Stop measurement")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip(
            "Turn off sources and apply the configured shutdown gas flows."
        )
        buttons.addWidget(self.stop_btn)
        actions_layout.addLayout(buttons)
        self.safety_note = hint(
            "Stopping turns off sources and applies the configured shutdown gas flows."
        )
        self.stop_btn.setToolTip(self.safety_note.text())
        return panel

    def build_monitor(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QHBoxLayout()
        self.readout = QLabel("Live readings · waiting for first sample")
        self.readout.setProperty("role", "sectionTitle")
        self.readout.setWordWrap(True)
        self.readout.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        heading.addWidget(self.readout, 1)
        self.plots = MeasurementPlots(self.config.hardware.mfc_controller.gas_names)
        plot_selector = QFrame()
        plot_selector.setObjectName("plotSelector")
        plot_buttons = QHBoxLayout(plot_selector)
        plot_buttons.setContentsMargins(3, 3, 3, 3)
        plot_buttons.setSpacing(2)
        short_labels = {
            "resistance_ohm": "R",
            "voltage_V": "V",
            "current_A": "I",
            "flows": "Flow",
        }
        for key, plot in self.plots.plots.items():
            title = plot.property("title")
            button = QToolButton()
            button.setText(short_labels[key])
            button.setCheckable(True)
            button.setChecked(True)
            button.setAccessibleName(f"Show {title} plot")
            button.setToolTip(
                f"Show or hide the {title.lower()} plot; recording continues."
            )
            button.toggled.connect(
                lambda checked, key=key: self.plots.toggle_plot(key, checked)
            )
            self.plots.visibility_buttons[key] = button
            plot_buttons.addWidget(button)
        heading.addWidget(plot_selector)
        heading.addSpacing(8)
        self.fit_plots_btn = QPushButton("Fit plots")
        self.fit_plots_btn.setToolTip("Show the full recorded time range in the plots.")
        heading.addWidget(self.fit_plots_btn)
        layout.addLayout(heading)
        metric_layout = QHBoxLayout()
        metric_layout.setSpacing(10)
        self.metrics = {}
        for key, name, unit in (
            ("resistance_ohm", "Resistance", "Ω"),
            ("voltage_V", "Voltage", "V"),
            ("current_A", "Current", "A"),
        ):
            card = QFrame()
            card.setObjectName("metricCard")
            box = QVBoxLayout(card)
            box.setContentsMargins(12, 10, 12, 10)
            box.addWidget(hint(name))
            value = QLabel(f"— {unit}")
            value.setProperty("role", "metricValue")
            box.addWidget(value)
            self.metrics[key] = value
            metric_layout.addWidget(card, 1)
        self.metric_row = QWidget()
        self.metric_row.setLayout(metric_layout)
        layout.addWidget(self.metric_row)
        self.plot_scroll = QScrollArea()
        self.plot_scroll.setWidgetResizable(True)
        self.plot_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.plot_scroll.setWidget(self.plots)
        self.plot_scroll.setMinimumHeight(0)
        self.plot_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored
        )
        layout.addWidget(self.plot_scroll, 1)
        self.fit_plots_btn.clicked.connect(self.plots.fit)
        return panel

    def build_details(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.details_toggle = QToolButton()
        self.details_toggle.setText("Session details")
        self.details_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.details_toggle.setCheckable(True)
        row.addWidget(self.details_toggle)
        self.saved_file = hint("Data is saved automatically while measuring.")
        self.saved_file.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        row.addWidget(self.saved_file, 1)
        self.guide_button = QPushButton("Operator guide")
        self.guide_button.clicked.connect(self.show_guide)
        row.addWidget(self.guide_button)
        layout.addLayout(row)
        self.console_display = QPlainTextEdit()
        self.console_display.setReadOnly(True)
        self.console_display.setMaximumBlockCount(1000)
        self.details_dialog = QDialog(self)
        self.details_dialog.setWindowTitle("Session details")
        self.details_dialog.resize(760, 400)
        details_layout = QVBoxLayout(self.details_dialog)
        details_layout.addWidget(self.console_display)
        self.details_dialog.finished.connect(
            lambda: self.details_toggle.setChecked(False)
        )
        self.details_toggle.toggled.connect(self.toggle_details)
        return container

    def toggle_details(self, expanded):
        self.details_dialog.setVisible(expanded)
        self.details_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def refresh_summary(self):
        setup = self.setup
        manual = setup.control_tabs.currentIndex() == 0
        total = sum(widget.value() for widget in setup.flow_inputs.values())
        setup.flow_total.setText(f"Total requested flow: {total:g} sccm")
        setup.flow_total.setToolTip(
            "Requested values. Actual gas flow is shown in the live plot."
        )
        self.start_manual_btn.setVisible(manual and not self.running)
        self.start_recipe_btn.setVisible(not manual and not self.running)
        self.apply_manual_btn.setVisible(manual and self.running)
        if self.running:
            self.summary.setText("Recording to CSV · changes to gas flows need Apply.")
            return
        instrument = (
            "One sensor" if setup.instrument.currentData() == "2400" else "Sensor array"
        )
        gas_text = (
            (f"{total:g} sccm requested" if total else "All gas flows are set to zero")
            if manual
            else "Gas flows and gate overrides follow the recipe"
        )
        self.summary.setText(
            f"{instrument} · {setup.wires.currentData()} terminals · "
            f"every {setup.interval.value():g} s\n{gas_text}"
        )

    def settings(self):
        return self.setup.settings()

    def reset_readings(self):
        self.plots.clear()
        for key, unit in (
            ("resistance_ohm", "Ω"),
            ("voltage_V", "V"),
            ("current_A", "A"),
        ):
            self.metrics[key].setText(f"— {unit}")
        self.readout.setText("Live readings · waiting for first sample")
        self.saved_file.setText(
            "Recording · CSV is written after every sensor reading."
        )

    def show_reading(self, data):
        self.plots.append(data)
        for key, unit in (
            ("resistance_ohm", "Ω"),
            ("voltage_V", "V"),
            ("current_A", "A"),
        ):
            value = data[key]
            self.metrics[key].setText(
                f"{value:.4g} {unit}" if value is not None else f"— {unit}"
            )
        text = f"Latest sensor: {data['device']} · {data['elapsed_s']:.1f} s"
        if "recipe_step" in data:
            text += (
                f"\nStep {data['recipe_step']}/{data['recipe_steps']}: {data['step']}"
                f" · total ≈ {data['recipe_total_s'] / 60:.2f} min"
                f" · remaining ≈ {data['recipe_remaining_s'] / 60:.2f} min"
            )
            details = []
            for ch, name in self.config.hardware.mfc_controller.gas_names.items():
                target = data[f"gas_{ch}_{name}_setpoint_sccm"]
                actual = data["flows"][ch]
                details.append(f"CH{ch} {name}: {target:g} / {actual:g}")
            text += "\nFlow set / actual (sccm): " + "; ".join(details)
        self.readout.setText(text)

    def select_compact_view(self):
        if not hasattr(self, "setup_view"):
            return
        compact = self.width() < 980
        self.setup_view.setVisible(not compact or self.compact_nav.currentIndex() == 0)
        self.monitor_view.setVisible(
            not compact or self.compact_nav.currentIndex() == 1
        )

    def show_monitor(self):
        if self.width() < 980:
            self.compact_nav.setCurrentIndex(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "monitor_view"):
            compact = self.width() < 980
            self.compact_nav.setVisible(compact)
            self.summary.setVisible(not compact)
            self.outer.setSpacing(8 if compact else 12)
            self.splitter.setOrientation(
                Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal
            )
            self.select_compact_view()

    def show_guide(self):
        from .widgets.operator_guide import OperatorGuide

        if not hasattr(self, "guide_dialog"):
            self.guide_dialog = OperatorGuide(self)
        self.guide_dialog.show()
        self.guide_dialog.raise_()

    def closeEvent(self, event):
        if self.running:
            event.ignore()
            self.close_requested.emit()
        else:
            event.accept()
