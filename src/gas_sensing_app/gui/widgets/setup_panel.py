"""Guided experiment preparation, independent of acquisition and window state."""

from dataclasses import replace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class IgnoreWheel:
    """Allow panel scrolling without accidentally changing experiment settings."""

    def wheelEvent(self, event):
        event.ignore()


class FlowInput(IgnoreWheel, QDoubleSpinBox):
    pass


class ChannelInput(IgnoreWheel, QSpinBox):
    pass


class ChoiceInput(IgnoreWheel, QComboBox):
    pass


def hint(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("role", "muted")
    return label


def number(value, minimum, maximum, decimals=4):
    widget = FlowInput()
    widget.setDecimals(decimals)
    widget.setRange(minimum, maximum)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
    return widget


def form_for(widget):
    form = QFormLayout(widget)
    form.setContentsMargins(16, 16, 16, 16)
    form.setVerticalSpacing(12)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form


class SetupPanel(QTabWidget):
    changed = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.setObjectName("setupTabs")
        self.build_measurement()
        self.build_gases()
        self.build_gate()
        # Keep the optional gate implementation available without exposing its tab.
        self.setTabVisible(2, False)
        for widget in self.findChildren(QComboBox):
            widget.currentIndexChanged.connect(self.changed)
        for widget in self.findChildren(QAbstractSpinBox):
            widget.valueChanged.connect(self.changed)
        self.gate_enabled.toggled.connect(self.changed)
        self.auto_range.toggled.connect(self.changed)
        self.auto_range.toggled.connect(self.topology_changed)
        self.control_tabs.currentChanged.connect(self.changed)
        self.instrument.currentIndexChanged.connect(self.instrument_changed)
        self.wires.currentIndexChanged.connect(self.topology_changed)
        self.measurement_mode.currentIndexChanged.connect(self.topology_changed)
        self.gate_enabled.toggled.connect(self.gate_changed)
        self.gate_mode.currentIndexChanged.connect(self.gate_changed)
        self.instrument_changed()
        self.measurement_mode.setCurrentIndex(
            max(0, self.measurement_mode.findData(config.measurement.mode))
        )
        self.gate_changed()

    def add_page(self, widget, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(widget)
        self.addTab(scroll, title)

    def build_measurement(self):
        cfg = self.config.measurement
        self.settings_group = QWidget()
        self.measurement_form = form_for(self.settings_group)
        form = self.measurement_form
        form.addRow(
            hint(
                "Choose the connected setup. "
                "Only the settings needed for it will appear."
            )
        )
        self.instrument = ChoiceInput()
        self.instrument.addItem("One sensor · Keithley 2400", "2400")
        self.instrument.addItem("Sensor array · 2700 + 7706", "2700")
        self.instrument.setCurrentIndex(self.instrument.findData(cfg.instrument))
        self.measurement_mode = ChoiceInput()
        self.wires = ChoiceInput()
        self.wires.addItem("2 terminals", 2)
        self.wires.addItem("4 terminals · Kelvin", 4)
        self.wires.setCurrentIndex(self.wires.findData(cfg.wire_mode))
        self.slot = ChannelInput()
        self.slot.setRange(1, 2)
        self.slot.setValue(cfg.slot)
        self.slot.setToolTip(
            "Physical rear slot containing the 7706 card: slot 1 uses channels "
            "101–120; slot 2 uses 201–220. Enter local channel numbers below."
        )
        self.first_channel, self.last_channel = ChannelInput(), QSpinBox()
        for widget, value in (
            (self.first_channel, cfg.first_channel),
            (self.last_channel, cfg.last_channel),
        ):
            widget.setRange(1, 20)
            widget.setValue(value)
        self.bias = number(cfg.bias_voltage, -210, 210)
        self.compliance = number(cfg.compliance, 1e-9, 1.05, 9)
        self.auto_range = QCheckBox("Choose resistance range automatically")
        self.auto_range.setChecked(cfg.auto_range)
        self.manual_range = number(cfg.manual_range, 1e-9, 1e12, 6)
        self.interval = number(cfg.interval_s, 0.01, 86400, 2)
        self.extra_inputs = {}
        for key, label, minimum, maximum, decimals, scale in (
            ("source_current", "Applied current (µA)", -1.05e6, 1.05e6, 6, 1e6),
            ("voltage_compliance", "Voltage limit (V)", 0.0002, 210, 4, 1),
            ("source_voltage_range", "Source voltage range (V)", 0.2, 200, 3, 1),
            ("source_current_range", "Source current range (µA)", 1, 1e6, 3, 1e6),
            ("voltage_range", "Measured voltage range (V)", 0.1, 1000, 3, 1),
            ("current_range", "Measured current range (µA)", 1, 1e6, 3, 1e6),
            ("settling_s", "Source settling delay (s)", 0, 60, 3, 1),
            ("nplc", "Integration time (NPLC)", 0.01, 50, 2, 1),
        ):
            widget = number(getattr(cfg, key) * scale, minimum, maximum, decimals)
            widget.setAccessibleName(label)
            self.extra_inputs[key] = (widget, scale)
        self.extra_checks = {}
        for key, label in (
            ("source_auto_range", "Automatic source range"),
            ("voltage_auto_range", "Voltage sense autorange"),
            ("current_auto_range", "Current sense autorange"),
            ("pulsed", "Pulse output"),
        ):
            widget = QCheckBox(label)
            widget.setChecked(getattr(cfg, key))
            widget.toggled.connect(self.changed)
            widget.toggled.connect(self.topology_changed)
            self.extra_checks[key] = widget
        self.extra_checks["pulsed"].setToolTip(
            "Source on → settling delay → measurement → high-impedance off. "
            "The interval sets the pause from previous off to next on."
        )
        self.extra_inputs["source_current"][0].setToolTip(
            "Commanded test current in µA. 0.5 µA = 0.0000005 A. "
            "Voltage compliance can reduce the actual current."
        )
        self.extra_inputs["voltage_compliance"][0].setToolTip(
            "Maximum voltage during fixed-current sourcing. At 0.5 µA and 2 V, "
            "the requested current can be maintained only up to about 4 MΩ. "
            "Above that, current is reduced to respect this limit."
        )
        self.extra_inputs["nplc"][0].setToolTip(
            "NPLC = number of power-line cycles integrated per conversion. "
            "Default 1 balances speed and noise rejection (20 ms at 50 Hz; "
            "16.7 ms at 60 Hz per conversion). Lower = faster, noisier. "
            "Higher = slower, more averaging; whole cycles reject line noise. "
            "Pulses stay on longer at higher NPLC. Autoranging, autozero and "
            "concurrent measurements add time. 2400: 0.01–10; 2700: 0.01–50."
        )
        self.extra_inputs["settling_s"][0].setToolTip(
            "Delay after applying the source and before acquisition. Default 10 ms "
            "is a starting point; increase if sensor/cable capacitance needs more "
            "settling. Actual on-time also includes integration and overhead."
        )
        for key in (
            "source_voltage_range",
            "source_current_range",
            "voltage_range",
            "current_range",
        ):
            self.extra_inputs[key][0].setToolTip(
                "Requested range capacity. Instrument selects the smallest supported "
                "range that accommodates this value. Source and same-quantity "
                "measurement ranges track each other on the 2400. A manual sense "
                "range can limit achievable compliance."
            )
        self.apply_range_btn = QPushButton("Apply range to next scan")
        self.apply_range_btn.setEnabled(False)
        for label, widget in (
            ("Connected setup", self.instrument),
            ("What to measure", self.measurement_mode),
            ("Sensor wiring", self.wires),
            ("Card slot", self.slot),
            ("First sensor channel", self.first_channel),
            ("Last sensor channel", self.last_channel),
            ("Applied voltage (V)", self.bias),
            ("Current limit (A)", self.compliance),
            ("Resistance autorange", self.auto_range),
            ("Resistance range (Ω)", self.manual_range),
            ("Read every (s)", self.interval),
        ):
            form.addRow(label, widget)
            widget.setAccessibleName(label)
        for key in (
            "source_current",
            "voltage_compliance",
            "source_auto_range",
            "source_voltage_range",
            "source_current_range",
            "voltage_auto_range",
            "voltage_range",
            "current_auto_range",
            "current_range",
            "pulsed",
            "settling_s",
            "nplc",
        ):
            if key in self.extra_checks:
                form.addRow(self.extra_checks[key])
            else:
                widget, _ = self.extra_inputs[key]
                form.addRow(widget.accessibleName(), widget)
        self.interval.setToolTip(
            "Target interval between sensor scans. Instrument readout may take longer."
        )
        form.addRow(self.apply_range_btn)
        self.manual_range.setToolTip(
            "2700: 100 Ω to 100 MΩ. The instrument chooses the smallest decade "
            "range that accommodates this value. Applies to all selected channels."
        )
        self.compliance.setToolTip(
            "Maximum allowed drain current. "
            "Use the laboratory-approved limit for your sensor."
        )
        self.bias.setToolTip(
            "2400 source voltage in fixed-voltage mode. The current limit may "
            "reduce the actual voltage. Independent of the gate supply."
        )
        next_button = QPushButton("Next: choose gas flows →")
        next_button.clicked.connect(lambda: self.setCurrentIndex(1))
        form.addRow(next_button)
        self.add_page(self.settings_group, "1  Measurement")

    def build_gases(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.addWidget(
            hint(
                "Set flows yourself, or load a saved recipe "
                "to run a sequence automatically."
            )
        )
        self.control_tabs = QTabWidget()
        manual = QWidget()
        gas_form = form_for(manual)
        self.flow_inputs = {}
        for channel, maximum in self.config.hardware.mfc_controller.range_sccm.items():
            name = (
                self.config.hardware.mfc_controller.gas_names[channel]
                .replace("_", " ")
                .capitalize()
            )
            widget = number(self.config.manual_flows.get(channel, 0), 0, maximum, 3)
            widget.setSuffix(" sccm")
            widget.setAccessibleName(f"{name} target flow")
            widget.setToolTip(f"Channel {channel} · allowed range 0–{maximum:g} sccm")
            self.flow_inputs[channel] = widget
            gas_form.addRow(name, widget)
        self.shutter_checkbox = QCheckBox("Expose sensor to light (open shutter)")
        self.shutter_checkbox.setEnabled(self.config.hardware.shutter.enabled)
        self.shutter_checkbox.setChecked(self.config.manual_shutter_open)
        gas_form.addRow(self.shutter_checkbox)
        self.flow_total = hint("Total requested flow: 0 sccm")
        gas_form.addRow(self.flow_total)
        gas_form.addRow(
            hint("During a sweep, changes wait until the entire sweep finishes.")
        )
        recipe = QWidget()
        recipe_layout = QVBoxLayout(recipe)
        self.load_recipe_btn = QPushButton("Choose recipe file…")
        self.recipe_label = QLabel("No recipe selected")
        self.recipe_label.setWordWrap(True)
        self.recipe_preview = QLabel(
            "Choose a saved YAML recipe to see its steps before starting."
        )
        self.recipe_preview.setWordWrap(True)
        self.recipe_preview.setProperty("role", "muted")
        for widget in (self.load_recipe_btn, self.recipe_label, self.recipe_preview):
            recipe_layout.addWidget(widget)
        recipe_layout.addStretch()
        self.control_tabs.addTab(manual, "Manual flows")
        self.control_tabs.addTab(recipe, "Saved recipe")
        self.control_tabs.setCurrentIndex(
            1 if self.config.acquisition_mode == "recipe" else 0
        )
        layout.addWidget(self.control_tabs)
        layout.addStretch()
        self.add_page(page, "2  Gases")

    def build_gate(self):
        cfg = self.config.gate
        self.gate_group = QWidget()
        self.gate_form = form_for(self.gate_group)
        form = self.gate_form
        form.addRow(
            hint(
                "Optional: apply a separate voltage to the sensor gate. "
                "Leave this off if your experiment does not use a gate."
            )
        )
        self.gate_enabled = QCheckBox("Enable gate voltage")
        self.gate_enabled.setChecked(cfg.enabled)
        self.gate_mode = ChoiceInput()
        self.gate_mode.addItem("Hold one voltage", "fixed")
        self.gate_mode.addItem("Sweep through voltages", "sweep")
        self.gate_mode.setCurrentIndex(self.gate_mode.findData(cfg.mode))
        form.addRow(self.gate_enabled)
        form.addRow("Voltage program", self.gate_mode)
        self.gate_inputs = {}
        for key, label, low, high, decimals in (
            ("voltage", "Gate voltage (V)", 0, cfg.max_voltage, 4),
            ("start", "Start voltage (V)", 0, cfg.max_voltage, 4),
            ("stop", "End voltage (V)", 0, cfg.max_voltage, 4),
            ("step", "Step size (V)", 0.0001, 65, 4),
            ("dwell_s", "Settle before reading (s)", 0.01, 86400, 2),
            ("current_limit", "Gate current limit (A)", 1e-9, 3, 9),
        ):
            widget = number(getattr(cfg, key), low, high, decimals)
            widget.setAccessibleName(label)
            self.gate_inputs[key] = widget
            form.addRow(label, widget)
        self.gate_note = hint("")
        self.gate_note.setObjectName("infoNote")
        form.addRow(self.gate_note)
        self.add_page(self.gate_group, "3  Gate (optional)")

    def instrument_changed(self):
        self.measurement_mode.blockSignals(True)
        self.measurement_mode.clear()
        self.measurement_mode.addItem(
            "Automatic ohms"
            if self.instrument.currentData() == "2400"
            else "Resistance",
            "resistance",
        )
        if self.instrument.currentData() == "2400":
            self.measurement_mode.addItem(
                "Fixed voltage · R, V & I", "constant_voltage"
            )
            self.measurement_mode.addItem(
                "Fixed current · R, V & I", "constant_current"
            )
        else:
            self.measurement_mode.addItem("Voltage", "voltage")
        self.measurement_mode.blockSignals(False)
        self.topology_changed()
        self.changed.emit()

    def update_source_controls(self):
        mux = self.instrument.currentData() == "2700"
        mode = self.measurement_mode.currentData()
        if not mode:
            return
        fixed = not mux and mode in ("constant_voltage", "constant_current")
        current_source = mode == "constant_current"
        checks = self.extra_checks
        inputs = self.extra_inputs
        visible_inputs = {"nplc"}
        if fixed:
            if current_source:
                visible_inputs.update(("source_current", "voltage_compliance"))
            if not checks["source_auto_range"].isChecked():
                visible_inputs.add(
                    "source_current_range" if current_source else "source_voltage_range"
                )
        sense_voltage = (mux and mode == "voltage") or (fixed and current_source)
        sense_current = fixed and not current_source
        if sense_voltage and not checks["voltage_auto_range"].isChecked():
            visible_inputs.add("voltage_range")
        if sense_current and not checks["current_auto_range"].isChecked():
            visible_inputs.add("current_range")
        if not mux:
            visible_inputs.add("settling_s")
        for key, (widget, _) in inputs.items():
            self.measurement_form.setRowVisible(widget, key in visible_inputs)
        for key, visible in (
            ("source_auto_range", fixed),
            ("voltage_auto_range", sense_voltage),
            ("current_auto_range", sense_current),
            ("pulsed", not mux),
        ):
            self.measurement_form.setRowVisible(checks[key], visible)
        inputs["nplc"][0].setMaximum(50 if mux else 10)
        inputs["voltage_range"][0].setRange(0.1 if mux else 0.2, 1000 if mux else 200)
        pulsed = not mux and checks["pulsed"].isChecked()
        self.measurement_form.labelForField(self.interval).setText(
            "Off time between pulses (s)" if pulsed else "Read every (s)"
        )
        self.interval.setToolTip(
            "Minimum time from previous output off to next output on. "
            "Flow readback, logging and gate operations can extend this interval."
            if pulsed
            else "Target interval between scans; readout may take longer."
        )

    def topology_changed(self):
        self.update_source_controls()
        mux = self.instrument.currentData() == "2700"
        fixed = not mux and self.measurement_mode.currentData() != "resistance"
        voltage = self.measurement_mode.currentData() == "voltage"
        if mux and voltage:
            self.wires.setCurrentIndex(0)
        self.wires.setEnabled(
            not getattr(self, "running", False) and not (mux and voltage)
        )
        four = self.wires.currentData() == 4
        for widget in (self.slot, self.first_channel, self.last_channel):
            self.measurement_form.setRowVisible(widget, mux)
        for widget in (self.first_channel, self.last_channel):
            widget.setMaximum(10 if four else 20)
        bias = not mux and self.measurement_mode.currentData() == "constant_voltage"
        self.measurement_form.setRowVisible(self.bias, bias)
        self.measurement_form.setRowVisible(self.compliance, bias)
        self.measurement_form.setRowVisible(self.auto_range, not voltage and not fixed)
        self.measurement_form.setRowVisible(
            self.manual_range,
            not voltage and not fixed and not self.auto_range.isChecked(),
        )
        self.measurement_form.setRowVisible(self.apply_range_btn, mux and not voltage)

    def set_running(self, running):
        self.running = running
        for widget in (
            self.instrument,
            self.measurement_mode,
            self.wires,
            self.slot,
            self.first_channel,
            self.last_channel,
            self.bias,
            self.compliance,
            self.interval,
        ):
            widget.setEnabled(not running)
        for widget, _ in self.extra_inputs.values():
            widget.setEnabled(not running)
        for widget in self.extra_checks.values():
            widget.setEnabled(not running)
        live_range = (
            self.instrument.currentData() == "2700"
            and self.measurement_mode.currentData() == "resistance"
        )
        self.auto_range.setEnabled(not running or live_range)
        self.manual_range.setEnabled(not running or live_range)
        self.apply_range_btn.setEnabled(running and live_range)
        if not running:
            self.topology_changed()

    def gate_changed(self):
        enabled = self.gate_enabled.isChecked()
        sweep = self.gate_mode.currentData() == "sweep"
        self.gate_form.setRowVisible(self.gate_mode, enabled)
        for key, widget in self.gate_inputs.items():
            visible = enabled and (
                key not in ("start", "stop", "step", "voltage")
                or (sweep if key != "voltage" else not sweep)
            )
            self.gate_form.setRowVisible(widget, visible)
        self.gate_note.setText(
            "Gate is off. No gate voltage will be applied. "
            "Recipe steps may override this setting."
            if not enabled
            else "Gas flow setpoints stay fixed throughout each sweep. "
            + (
                "Gate output is simulated in Mock mode."
                if self.config.hardware.use_mock
                else "Real gate control is not yet connected. "
                "Disable gate to run with real instruments."
            )
        )

    def settings(self):
        measurement = replace(
            self.config.measurement,
            instrument=self.instrument.currentData(),
            mode=self.measurement_mode.currentData(),
            wire_mode=self.wires.currentData(),
            slot=self.slot.value(),
            first_channel=self.first_channel.value(),
            last_channel=self.last_channel.value(),
            bias_voltage=self.bias.value(),
            compliance=self.compliance.value(),
            auto_range=self.auto_range.isChecked(),
            manual_range=self.manual_range.value(),
            interval_s=self.interval.value(),
            **{
                key: widget.value() / scale
                for key, (widget, scale) in self.extra_inputs.items()
            },
            **{key: widget.isChecked() for key, widget in self.extra_checks.items()},
        )
        gate = replace(
            self.config.gate,
            enabled=self.gate_enabled.isChecked(),
            mode=self.gate_mode.currentData(),
            **{key: widget.value() for key, widget in self.gate_inputs.items()},
        )
        measurement.validate()
        gate.points()
        return measurement, gate
