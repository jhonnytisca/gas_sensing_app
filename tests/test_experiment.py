import csv
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from gas_sensing_app.config.config import Config
from gas_sensing_app.config.models import GateSettings, MeasurementSettings
from gas_sensing_app.core.engine import ExperimentEngine
from gas_sensing_app.core.recipe import Stage, load_recipe
from gas_sensing_app.hardware.factory import HardwareFactory


@pytest.fixture
def config(tmp_path):
    template = (
        Path(__file__).parents[1] / "src/gas_sensing_app/assets/config.template.yaml"
    )
    path = tmp_path / "config.yaml"
    path.write_text(template.read_text())
    (tmp_path / "failure_gases.yaml").write_text(
        "mfc_flows: {1: 15, 2: 0, 3: 0, 4: 0}\n"
    )
    return Config(path).load()


class RecordingFactory(HardwareFactory):
    def __init__(self, config):
        super().__init__(config)
        self.events = []
        self.devices = {}
        self.fail_read = False
        self.fail_off = False

    def track(self, name, device):
        self.devices[name] = device
        for method in (
            "configure",
            "read",
            "output_on",
            "output_off",
            "set_voltage",
            "set_flow",
            "close",
        ):
            if not hasattr(device, method):
                continue
            original = getattr(device, method)

            def call(*args, original=original, method=method):
                self.events.append((name, method, args))
                if name == "meter" and method == "read" and self.fail_read:
                    raise RuntimeError("injected read failure")
                if name == "gate" and method == "output_off" and self.fail_off:
                    raise RuntimeError("injected output failure")
                return original(*args)

            setattr(device, method, call)
        return device

    def meter(self, settings):
        return self.track("meter", super().meter(settings))

    def gate(self):
        return self.track("gate", super().gate())

    def mfc(self):
        return self.track("mfc", super().mfc())


def test_live_range_applies_between_frames_and_is_saved(config):
    engine = ExperimentEngine(
        config, MeasurementSettings(instrument="2700", last_channel=2), GateSettings()
    )
    rows = []

    def on_data(row):
        rows.append(row)
        if len(rows) == 1:
            engine.update_resistance_range(False, 100000)

    engine.on_data = on_data
    try:
        engine.prepare()
        engine.acquire("test")
        engine.acquire("test")
        assert [r["resistance_range_mode"] for r in rows] == [
            "auto",
            "auto",
            "manual",
            "manual",
        ]
        assert rows[-1]["resistance_range_actual_ohm"] == 100000
        with open(engine.log_path) as stream:
            saved = list(csv.DictReader(stream))
        assert saved[-1]["resistance_range_requested_ohm"] == "100000"
        assert saved[-1]["resistance_range_actual_ohm"] == "100000"
        engine.update_resistance_range(True, 100000)
        engine.acquire("test")
        assert rows[-1]["resistance_range_mode"] == "auto"
    finally:
        engine.shutdown()


def test_sweep_csv_and_failure_shutdown(config):
    factory = RecordingFactory(config)
    gate = GateSettings(
        enabled=True, mode="sweep", start=0, stop=0.2, step=0.1, dwell_s=0.01
    )
    stage = Stage("exposure", 0.01, {1: 90, 2: 0, 3: 10, 4: 0}, False, gate)
    observed = []
    engine = ExperimentEngine(
        config, MeasurementSettings(), gate, [stage], factory=factory
    )

    def data(row):
        # The row must already be visible on disk before the GUI receives it.
        with open(engine.log_path) as stream:
            persisted = list(csv.DictReader(stream))
        assert len(persisted) == len(observed) + 1
        observed.append(row)

    engine.on_data = data
    engine.run()
    assert not engine.errors
    assert [row["gate_setpoint_V"] for row in observed] == [0, 0.1, 0.2]
    assert all(row["flows"][1] == 90 for row in observed)
    assert all(row["current_A"] > 0 for row in observed)
    assert not factory.devices["meter"].enabled
    assert not factory.devices["gate"].enabled
    assert factory.devices["mfc"].current_flows[1] == 15
    events = factory.events
    off = max(
        i for i, event in enumerate(events) if event[:2] == ("gate", "output_off")
    )
    purge = next(
        i for i, event in enumerate(events) if event == ("mfc", "set_flow", (1, 15.0))
    )
    assert off < purge


def test_partial_csv_preserved_and_other_cleanup_continues(config):
    factory = RecordingFactory(config)
    gate = GateSettings(enabled=True, mode="sweep", start=0, stop=0.2, dwell_s=0.01)
    stage = Stage("failure", 0.01, {1: 20, 2: 0, 3: 0, 4: 0}, False, gate)
    engine = ExperimentEngine(
        config, MeasurementSettings(), gate, [stage], factory=factory
    )

    def fail_after_row(row):
        factory.fail_read = True
        factory.fail_off = True

    engine.on_data = fail_after_row
    engine.run()
    assert len(engine.errors) == 2
    with open(engine.log_path) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert not factory.devices["meter"].enabled
    assert factory.devices["mfc"].current_flows[1] == 15
    assert factory.devices["mfc"].closed


def test_2700_four_wire_identity_and_missing_current(config):
    settings = MeasurementSettings(
        instrument="2700", wire_mode=4, slot=2, first_channel=1, last_channel=2
    )
    stage = Stage("scan", 0.01, {1: 0, 2: 0, 3: 0, 4: 0}, False, GateSettings())
    engine = ExperimentEngine(config, settings, GateSettings(), [stage])
    engine.run()
    assert not engine.errors
    with open(engine.log_path) as stream:
        rows = list(csv.DictReader(stream))
    assert [row["device"] for row in rows] == ["201+211", "202+212"]
    assert all(row["current_A"] == "" and row["voltage_V"] == "" for row in rows)


def test_stop_during_sweep_preserves_rows_and_applies_purge(config):
    gate = GateSettings(enabled=True, mode="sweep", stop=10, dwell_s=0.01)
    factory = RecordingFactory(config)
    engine = ExperimentEngine(config, MeasurementSettings(), gate, factory=factory)
    engine.on_data = lambda row: engine.stop()
    engine.run()
    with open(engine.log_path) as stream:
        assert len(list(csv.DictReader(stream))) == 1
    assert factory.devices["mfc"].current_flows[1] == 15


def test_invalid_recipe_and_gate_rejected_before_hardware(config, tmp_path):
    path = tmp_path / "recipe.yaml"
    path.write_text(
        yaml.safe_dump({"steps": [{"duration": 1, "mfc_flows": {1: 1001}}]})
    )
    with pytest.raises(ValueError):
        load_recipe(path, config, GateSettings())
    with pytest.raises(ValueError):
        MeasurementSettings(instrument="2700", wire_mode=4, last_channel=11).validate()
    with pytest.raises(ValueError):
        GateSettings(step=0).points()
    assert GateSettings(
        enabled=True, mode="sweep", start=1, stop=0, step=0.6
    ).points() == [1, 0.4, 0]
    real = replace(config, hardware=replace(config.hardware, use_mock=False))
    engine = ExperimentEngine(real, MeasurementSettings(), GateSettings(enabled=True))
    engine.run()
    assert "transport" in engine.errors[0]
    assert engine.meter is None and engine.mfc is None


def test_manual_flow_change_deferred_until_sweep_boundary(config):
    gate = GateSettings(enabled=True, mode="sweep", stop=0.1, dwell_s=0.01)
    rows = []
    engine = ExperimentEngine(config, MeasurementSettings(interval_s=0.01), gate)
    engine.update_manual(False, {1: 10})

    def data(row):
        rows.append(row)
        if len(rows) == 1:
            engine.update_manual(False, {1: 20})
        if len(rows) == 3:
            engine.stop()

    engine.on_data = data
    engine.run()
    assert rows[0]["flows"][1] == 10
    assert rows[1]["flows"][1] == 10
    assert rows[-1]["flows"][1] == 20


def test_startup_failure_still_applies_failure_gases(config):
    factory = RecordingFactory(config)

    def meter_failure(settings):
        raise RuntimeError("instrument unavailable")

    factory.meter = meter_failure
    engine = ExperimentEngine(
        config, MeasurementSettings(), GateSettings(), factory=factory
    )
    engine.run()
    assert "instrument unavailable" in engine.errors[0]
    assert factory.devices["mfc"].current_flows[1] == 15
    assert factory.devices["mfc"].closed
    assert engine.csv.file.closed


def test_disk_write_failure_stops_sources_and_keeps_prior_rows(config):
    gate = GateSettings(enabled=True, mode="sweep", stop=0.2, dwell_s=0.01)
    factory = RecordingFactory(config)
    engine = ExperimentEngine(config, MeasurementSettings(), gate, factory=factory)

    def disk_failure(row):
        raise OSError("disk full")

    engine.on_data = lambda row: setattr(engine.csv, "write", disk_failure)
    engine.run()
    assert "disk full" in engine.errors[0]
    with open(engine.log_path) as stream:
        assert len(list(csv.DictReader(stream))) == 1
    assert not factory.devices["gate"].enabled
    assert not factory.devices["meter"].enabled
    assert factory.devices["mfc"].current_flows[1] == 15
