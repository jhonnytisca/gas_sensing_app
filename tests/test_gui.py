import csv
from pathlib import Path

from PyQt6.QtCore import Qt

from gas_sensing_app.config.config import Config
from gas_sensing_app.controllers.dashboard_controller import DashboardController
from gas_sensing_app.gui.dashboard import Dashboard


def test_manual_window_lifecycle_and_linked_plots(qtbot, tmp_path):
    path = tmp_path / "config.yaml"
    template = (
        Path(__file__).parents[1]
        / "src/gas_sensing_app/assets/defaults/config.template.yaml"
    )
    path.write_text(template.read_text())
    (tmp_path / "failure_gases.yaml").write_text("mfc_flows: {1: 10}")
    config = Config(path).load()
    window = Dashboard(config)
    controller = DashboardController(window, config)
    qtbot.addWidget(window)
    window.resize(640, 480)
    window.show()
    qtbot.waitUntil(lambda: window.splitter.orientation() == Qt.Orientation.Vertical)
    assert window.width() == 640
    for key in ("resistance_ohm", "voltage_V", "current_A"):
        assert (
            window.plots.plots[key].getViewBox().linkedView(0)
            is window.plots.plots["flows"].getViewBox()
        )
    window.setup.interval.setValue(0.02)
    controller.start("manual")
    worker = controller.worker
    qtbot.waitUntil(lambda: bool(window.plots.history), timeout=3000)
    window.close()
    assert controller.closing
    qtbot.waitUntil(lambda: controller.worker is None, timeout=3000)
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=3000)
    with open(worker.engine.log_path) as stream:
        rows = list(csv.DictReader(stream))
    assert rows and rows[0]["current_A"]
    assert not worker.engine.meter.enabled
    assert worker.engine.mfc.current_flows[1] == 10
    controller.close_log()


def make_window(qtbot, tmp_path):
    path = tmp_path / "config.yaml"
    template = (
        Path(__file__).parents[1]
        / "src/gas_sensing_app/assets/defaults/config.template.yaml"
    )
    path.write_text(template.read_text())
    (tmp_path / "failure_gases.yaml").write_text("mfc_flows: {}")
    config = Config(path).load()
    config.logging.console_log.enabled = False
    window = Dashboard(config)
    controller = DashboardController(window, config)
    qtbot.addWidget(window)
    window.show()
    return window, controller


def test_compact_actions_and_conditional_setup(qtbot, tmp_path):
    window, controller = make_window(qtbot, tmp_path)
    window.resize(640, 480)
    qtbot.waitUntil(lambda: window.compact_nav.isVisible())
    compact_size = window.size()
    assert window.start_manual_btn.isVisible()
    assert window.stop_btn.isVisible()
    setup = window.setup
    assert setup.slot.isHidden()
    setup.instrument.setCurrentIndex(1)
    setup.wires.setCurrentIndex(1)
    assert not setup.slot.isHidden()
    assert setup.last_channel.maximum() == 10
    setup.measurement_mode.setCurrentIndex(1)
    assert setup.wires.currentData() == 2
    assert not setup.wires.isEnabled()
    setup.setCurrentIndex(2)
    assert setup.gate_inputs["start"].isHidden()
    setup.gate_enabled.setChecked(True)
    setup.gate_mode.setCurrentIndex(1)
    assert not setup.gate_inputs["start"].isHidden()
    assert setup.gate_inputs["voltage"].isHidden()
    window.show_monitor()
    assert window.stop_btn.isVisible()
    assert window.monitor_view.isVisible()
    assert window.size() == compact_size
    controller.close_log()


def test_fixed_voltage_and_resistance_range_controls(qtbot, tmp_path):
    window, controller = make_window(qtbot, tmp_path)
    setup = window.setup
    assert setup.measurement_mode.currentData() == "constant_voltage"
    assert not setup.bias.isHidden()
    setup.bias.setValue(0.5)
    setup.compliance.setValue(0.0001)
    setup.auto_range.setChecked(False)
    assert setup.manual_range.isHidden()  # Manual ohms uses source/sense ranges.
    setup.manual_range.setValue(2000000)
    measurement, _ = setup.settings()
    assert measurement.bias_voltage == 0.5
    assert measurement.compliance == 0.0001
    assert measurement.manual_range == 2000000
    assert not measurement.auto_range
    setup.auto_range.setChecked(True)
    assert setup.manual_range.isHidden()
    setup.measurement_mode.setCurrentIndex(0)
    assert setup.bias.isHidden()
    setup.instrument.setCurrentIndex(1)
    assert setup.bias.isHidden()
    assert not setup.auto_range.isHidden()
    controller.close_log()


def test_theme_changes_existing_curves_and_guide_opens(qtbot, tmp_path):
    from gas_sensing_app.gui.styles.theme_manager import Theme

    window, controller = make_window(qtbot, tmp_path)
    window.show_reading(
        {
            "device": "single",
            "elapsed_s": 1.0,
            "resistance_ohm": 1000,
            "voltage_V": 0.1,
            "current_A": 0.0001,
            "measurement_status": "simulated",
            "gate_setpoint_V": None,
            "gate_voltage_V": None,
            "flows": {1: 100},
        }
    )
    curve = window.plots.curves[("resistance_ohm", "single")]
    dark_color = curve.opts["pen"].color().name()
    qtbot.mouseClick(window.theme_selector.group.button(1), Qt.MouseButton.LeftButton)
    assert window.plots.theme == Theme.LIGHT
    assert curve.opts["pen"].color().name() != dark_color
    assert (
        window.plots.plots["resistance_ohm"].backgroundBrush().color().name()
        == "#ffffff"
    )
    window.show_guide()
    assert "Connect" in window.guide_dialog.browser.toPlainText()
    window.guide_dialog.search.setText("shutdown")
    window.guide_dialog.find_next()
    assert window.guide_dialog.browser.textCursor().selectedText().lower() == "shutdown"
    window.guide_dialog.close()
    controller.close_log()


def test_recipe_preview_validates_before_enabling_start(qtbot, tmp_path):
    window, controller = make_window(qtbot, tmp_path)
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text(
        "steps:\n  - name: Baseline\n    duration: 1\n    mfc_flows: {1: 100}\n"
    )
    controller.load_recipe_file(str(recipe))
    assert window.start_recipe_btn.isEnabled()
    assert "Baseline" in window.setup.recipe_preview.text()
    assert "100 sccm" in window.setup.recipe_preview.text()
    assert "Estimated total duration" in window.setup.recipe_preview.text()
    assert "CH1" in window.setup.recipe_preview.text()
    recipe.write_text("steps: []")
    controller.load_recipe_file(str(recipe))
    assert not window.start_recipe_btn.isEnabled()
    assert controller.recipe_path is None
    assert window.status_label.property("state") == "error"
    window.details_dialog.close()
    controller.close_log()


def test_2700_live_range_and_plot_visibility(qtbot, tmp_path):
    window, controller = make_window(qtbot, tmp_path)
    setup = window.setup
    setup.instrument.setCurrentIndex(1)
    plots = window.plots
    assert plots.plots["voltage_V"].isHidden()
    assert plots.plots["current_A"].isHidden()
    assert not plots.plots["resistance_ohm"].isHidden()
    setup.interval.setValue(0.02)
    controller.start("manual")
    try:
        qtbot.waitUntil(lambda: bool(plots.history), timeout=3000)
        assert setup.auto_range.isEnabled()
        assert not setup.instrument.isEnabled()
        setup.auto_range.setChecked(False)
        setup.manual_range.setValue(100000)
        assert not setup.wires.isEnabled()
        qtbot.mouseClick(setup.apply_range_btn, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: not controller.worker.engine.measurement.auto_range)
        plots.visibility_buttons["flows"].click()
        assert plots.plots["flows"].isHidden()
        assert plots.plots["resistance_ohm"].getViewBox().linkedView(0) is None
        plots.visibility_buttons["flows"].click()
        assert not plots.plots["flows"].isHidden()
    finally:
        controller.stop()
        qtbot.waitUntil(lambda: controller.worker is None, timeout=3000)
        controller.close_log()


def test_fixed_current_controls_roundtrip(qtbot, tmp_path):
    window, controller = make_window(qtbot, tmp_path)
    setup = window.setup
    setup.measurement_mode.setCurrentIndex(
        setup.measurement_mode.findData("constant_current")
    )
    assert not setup.extra_inputs["source_current"][0].isHidden()
    assert setup.extra_inputs["source_current"][0].value() == 0.5
    assert setup.extra_inputs["voltage_compliance"][0].value() == 2
    setup.extra_checks["pulsed"].setChecked(True)
    setup.extra_checks["source_auto_range"].setChecked(False)
    setup.extra_checks["voltage_auto_range"].setChecked(False)
    assert not setup.extra_inputs["source_current_range"][0].isHidden()
    assert not setup.extra_inputs["voltage_range"][0].isHidden()
    assert setup.extra_checks["current_auto_range"].isHidden()
    assert "Off time" in setup.measurement_form.labelForField(setup.interval).text()
    measurement, _ = setup.settings()
    assert measurement.source_current == 0.5e-6
    assert measurement.pulsed and measurement.voltage_compliance == 2
    setup.set_running(True)
    assert not setup.extra_inputs["source_current"][0].isEnabled()
    assert not setup.extra_checks["pulsed"].isEnabled()
    controller.close_log()


def test_live_plot_spikes_zoom_and_resume(qtbot):
    from gas_sensing_app.gui.widgets.plots import MeasurementPlots

    plots = MeasurementPlots({1: "gas"})
    qtbot.addWidget(plots)
    plots.show()
    for i in range(1001):
        plots.append(
            {
                "device": "single",
                "elapsed_s": i,
                "resistance_ohm": 1e9 if i == 900 else 1000,
                "voltage_V": 1,
                "current_A": 1e-6,
                "flows": {1: 10},
                "gate_setpoint_V": None,
            }
        )
    assert plots.plots["resistance_ohm"].viewRange()[1][1] < 1e6
    assert plots.plots["resistance_ohm"].viewRange()[0][0] > 600
    plots.plots["resistance_ohm"].getViewBox().sigRangeChangedManually.emit(
        [True, True]
    )
    assert not plots.live
    plots.fit()
    assert plots.plots["resistance_ohm"].viewRange()[1][1] > 1e9
    assert plots.plots["resistance_ohm"].viewRange()[0][0] <= 0
    plots.append(
        {
            "device": "single",
            "elapsed_s": 1200,
            "resistance_ohm": 1000,
            "voltage_V": 1,
            "current_A": 1e-6,
            "flows": {1: 10},
            "gate_setpoint_V": None,
        }
    )
    assert plots.plots["resistance_ohm"].viewRange()[0][0] <= 0
    assert plots.plots["resistance_ohm"].viewRange()[0][1] >= 1200
    plots.pause_live()
    paused = plots.plots["resistance_ohm"].viewRange()
    plots.append(
        {
            "device": "single",
            "elapsed_s": 1500,
            "resistance_ohm": 1000,
            "voltage_V": 1,
            "current_A": 1e-6,
            "flows": {1: 10},
            "gate_setpoint_V": None,
        }
    )
    assert plots.plots["resistance_ohm"].viewRange() == paused
    plots.resume_live()
    assert plots.live and plots.robust
    assert plots.plots["resistance_ohm"].viewRange()[1][1] < 1e6
    assert max(plots.history[("resistance_ohm", "single")][1]) == 1e9


def test_load_save_profile_replaces_form_and_preserves_local_ports(qtbot, tmp_path):
    window, controller = make_window(qtbot, tmp_path)
    window.config.hardware.keithley_2400.port = "ASRL9::INSTR"
    setup = window.setup
    setup.measurement_mode.setCurrentIndex(
        setup.measurement_mode.findData("constant_current")
    )
    setup.extra_inputs["settling_s"][0].setValue(0.02)
    setup.extra_inputs["voltage_compliance"][0].setValue(7)
    setup.extra_checks["pulsed"].setChecked(True)
    setup.flow_inputs[1].setValue(42)
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text("steps: [{name: Gas, duration: 1, mfc_flows: {1: 10}}]")
    controller.load_recipe_file(str(recipe))
    setup.control_tabs.setCurrentIndex(1)
    profile = tmp_path / "saved.yaml"
    assert controller.save_configuration_file(profile)
    setup.extra_inputs["voltage_compliance"][0].setValue(2)
    assert controller.load_configuration_file(profile)
    assert window.setup is not setup
    assert window.setup.extra_inputs["voltage_compliance"][0].value() == 7
    assert window.setup.extra_inputs["settling_s"][0].value() == 0.02
    assert window.setup.flow_inputs[1].value() == 42
    assert window.config.hardware.keithley_2400.port == "ASRL9::INSTR"
    assert window.setup.control_tabs.currentIndex() == 1
    assert "Gas" in window.setup.recipe_preview.text()
    assert window.start_recipe_btn.isEnabled()
    # New form controls are reconnected, including recipe/range behavior.
    window.setup.control_tabs.setCurrentIndex(0)
    assert window.start_manual_btn.isVisible()
    assert not window.setup.isTabVisible(2)
    good_setup = window.setup
    profile.write_text("configuration_version: 200")
    assert not controller.load_configuration_file(profile)
    assert window.setup is good_setup
    assert "Configuration not loaded" in window.status_label.text()
    window.details_dialog.close()
    controller.close_log()


def test_connection_dialog_discovery_manual_addresses_and_cancel(
    qtbot, tmp_path, monkeypatch
):
    from gas_sensing_app.gui.connections_dialog import ConnectionsDialog

    window, controller = make_window(qtbot, tmp_path)
    monkeypatch.setattr(
        "gas_sensing_app.gui.connections_dialog.scan_resources",
        lambda: {
            "serial": [{"device": "COM7", "description": "USB adapter", "hwid": "123"}],
            "visa": ["ASRL7::INSTR"],
            "error": None,
        },
    )
    dialog = ConnectionsDialog(window.config, window.config.measurement, window)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(lambda: "Discovery complete" in dialog.status.text())
    qtbot.waitUntil(lambda: dialog.worker is None)
    assert window.config.hardware.keithley_2400.port == ""
    box = dialog.ports["keithley_2400"]
    box.setCurrentIndex(box.findData("ASRL7::INSTR"))
    assert dialog.port_value(box) == "ASRL7::INSTR"
    dialog.simulated.setChecked(False)
    dialog.shutter_enabled.setChecked(False)
    dialog.validate_and_accept()
    assert "MFC" in dialog.status.text().upper()
    dialog.ports["mfc_controller"].setEditText("COM8")
    dialog.validate_and_accept()
    assert dialog.config.hardware.mfc_controller.port == "ASRL8::INSTR"
    # No changes leak from the dialog until controller persistence succeeds.
    assert window.config.hardware.mfc_controller.port == ""
    controller.close_log()


def test_profile_buttons_disabled_during_acquisition(qtbot, tmp_path):
    import json

    window, controller = make_window(qtbot, tmp_path)
    profile = tmp_path / "experiment.yaml"
    assert controller.save_configuration_file(profile)
    window.setup.interval.setValue(0.02)
    controller.start("manual")
    worker = controller.worker
    try:
        qtbot.waitUntil(lambda: bool(window.plots.history), timeout=3000)
        assert not window.load_config_btn.isEnabled()
        assert not window.connections_btn.isEnabled()
        assert not controller.load_configuration_file(profile)
    finally:
        controller.stop()
        qtbot.waitUntil(lambda: controller.worker is None, timeout=3000)
        controller.close_log()
    assert window.load_config_btn.isEnabled() and window.connections_btn.isEnabled()
    metadata = json.loads(
        Path(worker.engine.log_path).with_suffix(".metadata.json").read_text()
    )
    assert metadata["configuration_source"]["name"] == "experiment.yaml"
    assert metadata["configuration_source"]["sha256"]
    assert metadata["resolved_connections"]["keithley_2400"]["port"] == ""


def test_missing_real_ports_prompt_before_creating_worker(qtbot, tmp_path, monkeypatch):
    from unittest.mock import Mock

    window, controller = make_window(qtbot, tmp_path)
    window.config.hardware.use_mock = False
    prompt = Mock(return_value=False)
    monkeypatch.setattr(controller, "configure_devices", prompt)
    controller.start("manual")
    prompt.assert_called_once()
    assert controller.worker is None
    assert not window.running
    controller.close_log()


def test_sample_notes_profile_and_metadata_only(qtbot, tmp_path):
    import json

    window, controller = make_window(qtbot, tmp_path)
    panel = window.sample_notes
    assert not panel.body.isHidden()
    label = "SnO₂ · sample B / device 03"
    notes = (
        "Prepared yesterday.\nSpecial condition: 20 ms settling.\n"
        "Gas response observation."
    )
    panel.sample_label.setText(label)
    panel.device.setText("102,103,106")
    panel.experiment_name.setText("NO2")
    panel.experiment_notes.setPlainText(notes)
    profile = tmp_path / "sample.yaml"
    assert controller.save_configuration_file(profile)
    panel.sample_label.clear()
    assert controller.load_configuration_file(profile)
    panel = window.sample_notes
    assert not panel.body.isHidden()
    assert panel.values() == {
        "sample_name": label,
        "device": "102,103,106",
        "experiment_name": "NO2",
        "description": notes,
    }
    window.setup.interval.setValue(0.02)
    controller.start("manual")
    worker = controller.worker
    try:
        qtbot.waitUntil(lambda: bool(window.plots.history), timeout=3000)
        assert panel.sample_label.isReadOnly()
        assert panel.experiment_notes.isReadOnly()
    finally:
        controller.stop()
        qtbot.waitUntil(lambda: controller.worker is None, timeout=3000)
        controller.close_log()
    assert not panel.sample_label.isReadOnly()
    assert not panel.experiment_notes.isReadOnly()
    panel.experiment_notes.setPlainText("Notes for the next experiment")
    metadata = json.loads(
        Path(worker.engine.log_path).with_suffix(".metadata.json").read_text()
    )
    assert metadata["sample_name"] == label
    assert metadata["description"] == notes
    assert metadata["device"] == "102,103,106"
    assert metadata["experiment_name"] == "NO2"
    assert "D102,103,106" in Path(worker.engine.log_path).parent.name
    assert (Path(worker.engine.log_path).parent / "plot.png").is_file()
    with open(worker.engine.log_path) as stream:
        reader = csv.DictReader(stream)
        assert "sample_label" not in reader.fieldnames
        assert "experiment_notes" not in reader.fieldnames
        assert list(reader)
    content = Path(worker.engine.log_path).read_text()
    assert label not in content and "Prepared yesterday" not in content


def test_save_configuration_named_folder_and_replace_confirmation(
    qtbot, tmp_path, monkeypatch
):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox

    window, controller = make_window(qtbot, tmp_path)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("Gas test", True))
    recipe = tmp_path / "source.yaml"
    recipe.write_text("steps: [{duration: 1, mfc_flows: {1: 10}}]")
    controller.load_recipe_file(str(recipe))
    controller.save_configuration()
    folder = tmp_path / "configurations" / "Gas test"
    assert {p.name for p in folder.iterdir()} == {
        "Gas test.config.yaml",
        "Gas test.recipe.yaml",
    }
    previous = (folder / "Gas test.config.yaml").read_bytes()
    window.setup.flow_inputs[1].setValue(42)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    controller.save_configuration()
    assert (folder / "Gas test.config.yaml").read_bytes() == previous
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    controller.save_configuration()
    assert controller.load_configuration_file(folder / "Gas test.config.yaml")
    assert window.setup.flow_inputs[1].value() == 42
    assert controller.configurations_dir == tmp_path / "configurations"
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("../escape", True))
    controller.save_configuration()
    assert "without path separators" in window.status_label.text()
    assert not (tmp_path / "escape").exists()
    controller.close_log()


def test_workspace_configuration_keeps_shared_save_and_console_folders(qtbot, tmp_path):
    from gas_sensing_app.config.workspace import initialize_workspace

    config = initialize_workspace(tmp_path)
    window = Dashboard(config)
    controller = DashboardController(window, config)
    qtbot.addWidget(window)
    root = tmp_path / "workspace"
    folder = root / "configurations/test"
    try:
        assert Path(controller.console_log.name).parent == root / "console_logs"
        assert controller.save_configuration_file(folder, bundle=True)
        assert controller.load_configuration_file(folder / "test.config.yaml")
        assert controller.configurations_dir == root / "configurations"
        assert Path(controller.console_log.name).parent == root / "console_logs"
        assert not (folder / "console_logs").exists()
    finally:
        controller.close_log()
