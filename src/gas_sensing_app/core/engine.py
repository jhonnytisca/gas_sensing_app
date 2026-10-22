"""Experiment lifecycle independent of Qt: configure, run, persist, safe shutdown."""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from gas_sensing_app.config.config import load_failure_flows
from gas_sensing_app.config.validation import finite, flows
from gas_sensing_app.hardware.factory import HardwareFactory

from .storage import MeasurementCSV


class ExperimentEngine:
    def __init__(
        self,
        config,
        measurement,
        gate,
        stages=None,
        factory=None,
        on_data=None,
        on_status=None,
        on_error=None,
    ):
        self.config, self.measurement, self.gate_settings = config, measurement, gate
        self.stages = stages
        self.factory = factory or HardwareFactory(config)
        self.on_data = on_data or (lambda row: None)
        self.on_status = on_status or (lambda text: None)
        self.on_error = on_error or (lambda text: None)
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.pending = None
        self.meter = self.gate = self.mfc = self.shutter = self.csv = None
        self.log_path = None
        self.failure_flows = {}
        self.targets = dict.fromkeys(config.hardware.mfc_controller.range_sccm, 0.0)
        self.shutter_open = False
        self.gate_target = None
        self.errors = []
        self.started = 0
        self.operation = "preparing acquisition"
        self.active_gate = None

    def update_manual(self, shutter_open, targets):
        targets = flows(targets, self.config.hardware.mfc_controller.range_sccm)
        with self.lock:
            self.pending = (bool(shutter_open), targets)

    def stop(self):
        self.cancel.set()

    def report_error(self, text):
        self.errors.append(text)
        self.on_error(text)

    def run(self):
        try:
            if self.cancel.is_set():
                return
            self.prepare()
            if self.stages:
                for stage in self.stages:
                    if self.cancel.is_set():
                        break
                    self.apply_flows(stage.flows, stage.shutter_open)
                    self.on_status(f"Stage: {stage.name}")
                    self.run_stage(stage.name, stage.duration, stage.gate)
            else:
                self.apply_flows(self.targets, False)
                self.on_status("Manual acquisition")
                while not self.cancel.is_set():
                    with self.lock:
                        pending, self.pending = self.pending, None
                    if pending:
                        self.apply_flows(pending[1], pending[0])
                    # Manual updates are applied between complete sweeps only.
                    self.run_stage(
                        "MANUAL", self.measurement.interval_s, self.gate_settings
                    )
        except Exception as exc:
            self.report_error(f"Acquisition failed ({self.operation}): {exc}")
        finally:
            self.shutdown()
        return self.log_path

    def prepare(self):
        self.measurement.validate()
        self.gate_settings.points()
        self.failure_flows = load_failure_flows(self.config)
        gates = (
            [stage.gate for stage in self.stages]
            if self.stages
            else [self.gate_settings]
        )
        for gate in gates:
            self.factory.validate(gate)
        self.on_status("Preparing instruments")
        cfg = self.config.logging.data_log
        self.csv = MeasurementCSV(
            Path(self.config.base_dir) / cfg.folder,
            cfg.filename_prefix,
            self.config.hardware.mfc_controller.gas_names,
        )
        self.log_path = str(self.csv.path)
        # Persist the file header before any hardware is energized.
        self.operation = "connecting/configuring ROD-4"
        self.on_status(self.operation)
        self.mfc = self.factory.mfc()
        self.operation = "connecting/configuring shutter"
        self.shutter = self.factory.shutter()
        if self.shutter:
            self.shutter.set_open(False)
        self.operation = f"connecting Keithley {self.measurement.instrument}"
        self.on_status(self.operation)
        self.meter = self.factory.meter(self.measurement)
        if any(g.enabled for g in gates):
            self.operation = "connecting/configuring gate"
            self.gate = self.factory.gate()
            self.gate.output_off()
        self.operation = f"configuring Keithley {self.measurement.instrument}"
        self.on_status(self.operation)
        self.meter.configure(self.measurement)
        self.started = time.monotonic()

    def apply_flows(self, targets, shutter_open):
        for ch, value in targets.items():
            if self.cancel.is_set():
                return
            self.operation = f"setting ROD-4 channel {ch} flow"
            self.mfc.set_flow(ch, value)
        self.targets = dict(targets)
        if self.shutter:
            self.operation = "setting shutter position"
            self.shutter.set_open(shutter_open)
        self.shutter_open = shutter_open

    def run_stage(self, name, duration, gate):
        if self.cancel.is_set():
            return
        start = time.monotonic()
        gate_changed = gate != self.active_gate
        if self.gate and gate_changed:
            self.gate.output_off()
            if gate.enabled:
                self.gate.configure(gate.current_limit)
        self.active_gate = gate
        if gate.enabled and gate.mode == "sweep":
            for point in gate.points():
                if self.cancel.is_set():
                    return
                self.gate_target = point
                self.gate.set_voltage(point)
                self.gate.output_on()
                # Allow the gate to settle, then take a complete sensor frame.
                if self.cancel.wait(gate.dwell_s):
                    return
                self.acquire(name)
            # A stage never changes gas flows midway through a sweep.
            # If duration exceeds sweep time, hold the last gate point and sample.
        else:
            self.gate_target = gate.voltage if gate.enabled else None
            if gate.enabled and gate_changed:
                self.gate.set_voltage(gate.voltage)
                self.gate.output_on()
                if self.cancel.wait(gate.dwell_s):
                    return
        self.hold_and_sample(
            name, duration, start, first=not (gate.enabled and gate.mode == "sweep")
        )

    def hold_and_sample(self, name, duration, start, first):
        while not self.cancel.is_set() and (
            first or time.monotonic() - start < duration
        ):
            first = False
            tick = time.monotonic()
            self.acquire(name)
            remaining = duration - (time.monotonic() - start)
            self.cancel.wait(
                max(
                    0,
                    min(
                        remaining,
                        self.measurement.interval_s - (time.monotonic() - tick),
                    ),
                )
            )

    def acquire(self, stage_name):
        settings = self.measurement
        for ch in settings.channels:
            if self.cancel.is_set():
                return
            self.operation = f"reading Keithley {settings.instrument}, channel {ch}"
            reading = self.meter.read(ch)
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            elapsed = time.monotonic() - self.started
            self.operation = "reading ROD-4 flows"
            actual = {
                key: finite(
                    self.mfc.get_actual_flow(key), f"MFC readback {key}", -float("inf")
                )
                for key in self.targets
            }
            self.operation = "reading gate voltage"
            gate_v = (
                self.gate.read_voltage()
                if self.gate and self.gate_target is not None
                else None
            )
            if gate_v is not None:
                gate_v = finite(gate_v, "gate readback", -float("inf"))
            sense = ch + 10 if ch is not None and settings.wire_mode == 4 else None
            row = {
                "timestamp": timestamp,
                "elapsed_s": elapsed,
                "step": stage_name,
                "device": f"{ch}+{sense}" if sense else str(ch) if ch else "single",
                "slot": settings.slot if ch else None,
                "channel": ch,
                "sense_channel": sense,
                "wire_mode": settings.wire_mode,
                "resistance_ohm": reading.resistance,
                "voltage_V": reading.voltage,
                "current_A": reading.current,
                "measurement_status": reading.status,
                "gate_setpoint_V": self.gate_target,
                "gate_voltage_V": gate_v,
                "gate_status": "disabled"
                if self.gate_target is None
                else "measured"
                if gate_v is not None
                else "readback_unavailable",
                "shutter_open": int(self.shutter_open),
            }
            for key, gas_name in self.config.hardware.mfc_controller.gas_names.items():
                row[f"gas_{key}_{gas_name}_setpoint_sccm"] = self.targets[key]
                row[f"gas_{key}_{gas_name}_actual_sccm"] = actual[key]
            self.operation = "saving measurement CSV"
            self.csv.write(row)
            self.on_data(dict(row, flows=actual))

    def shutdown(self):
        def attempt(label, operation):
            try:
                operation()
            except Exception as exc:
                self.report_error(f"Shutdown {label}: {exc}")

        # Stop all sources first. Each cleanup action is attempted independently.
        if self.gate:
            attempt("gate output off", self.gate.output_off)
        if self.meter:
            attempt("meter output off / channels open", self.meter.output_off)
        if self.shutter:
            attempt("shutter closed", lambda: self.shutter.set_open(False))
        if self.mfc:
            for ch in self.targets:
                attempt(
                    f"gas {ch}",
                    lambda ch=ch: self.mfc.set_flow(
                        ch, self.failure_flows.get(ch, 0.0)
                    ),
                )
        for name in ("gate", "meter", "shutter", "mfc", "csv"):
            device = getattr(self, name)
            if device:
                attempt(f"close {name}", device.close)
        self.on_status(
            "Failed — inspect errors"
            if self.errors
            else "Stopped"
            if self.cancel.is_set()
            else "Complete"
        )
