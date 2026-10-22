import csv
from pathlib import Path

from PyQt6.QtCore import Qt

from gas_sensing_app.config.config import Config
from gas_sensing_app.controllers.dashboard_controller import DashboardController
from gas_sensing_app.gui.dashboard import Dashboard


def test_manual_window_lifecycle_and_linked_plots(qtbot, tmp_path):
    path = tmp_path / "config.yaml"
    template = (
        Path(__file__).parents[1] / "src/gas_sensing_app/assets/config.template.yaml"
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
        Path(__file__).parents[1] / "src/gas_sensing_app/assets/config.template.yaml"
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
    assert not setup.manual_range.isHidden()
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
    assert "automatically" in setup.capability_note.text()
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
