"""Single owner of run state, GUI actions and worker lifecycle."""

from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFileDialog

from gas_sensing_app.config.config import load_failure_flows
from gas_sensing_app.core.recipe import load_recipe
from gas_sensing_app.core.worker import ExperimentWorker
from gas_sensing_app.gui.styles.theme_manager import load_theme, refresh_style
from gas_sensing_app.hardware.factory import HardwareFactory


class DashboardController:
    def __init__(self, window, config):
        self.window, self.config = window, config
        self.worker = None
        self.recipe_path = None
        self.closing = False
        self.console_log = None
        console = config.logging.console_log
        if console.enabled:
            folder = Path(config.base_dir) / console.folder
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
            self.console_log = (folder / f"{console.filename_prefix}_{stamp}.log").open(
                "x", encoding="utf-8"
            )
        window.theme_selector.currentIndexChanged.connect(self.change_theme)
        window.setup.load_recipe_btn.clicked.connect(self.select_recipe)
        window.start_recipe_btn.clicked.connect(lambda: self.start("recipe"))
        window.start_manual_btn.clicked.connect(lambda: self.start("manual"))
        window.apply_manual_btn.clicked.connect(self.apply_manual)
        window.setup.apply_range_btn.clicked.connect(self.apply_range)
        window.stop_btn.clicked.connect(self.stop)
        window.close_requested.connect(self.close_requested)
        window.destroyed.connect(self.close_log)

    def log(self, text):
        self.window.console_display.appendPlainText(text)
        if self.console_log:
            self.console_log.write(f"{datetime.now(timezone.utc).isoformat()} {text}\n")
            self.console_log.flush()

    def close_log(self):
        if self.console_log:
            self.console_log.close()
            self.console_log = None

    def change_theme(self):
        theme = self.window.theme_selector.currentData()
        self.window.setStyleSheet(load_theme(theme))
        self.window.plots.apply_theme(theme)

    def select_recipe(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Select recipe", self.config.base_dir, "YAML (*.yaml *.yml)"
        )
        if path:
            self.load_recipe_file(path)

    def load_recipe_file(self, path):
        try:
            _, gate = self.window.settings()
            stages = load_recipe(path, self.config, gate)
        except Exception as exc:
            self.recipe_path = None
            self.window.start_recipe_btn.setEnabled(False)
            self.window.setup.recipe_label.setText("Recipe could not be loaded")
            self.window.setup.recipe_preview.setText(str(exc))
            self.error(str(exc))
            return
        self.recipe_path = path
        self.window.setup.recipe_label.setText(Path(path).name)
        self.window.setup.recipe_label.setToolTip(str(path))
        lines = []
        for index, stage in enumerate(stages, 1):
            total = sum(stage.flows.values())
            gate_text = stage.gate.mode if stage.gate.enabled else "off"
            lines.append(
                f"{index}. {stage.name} · at least {stage.duration:g} s\n"
                f"   Total flow {total:g} sccm · gate {gate_text}"
            )
        self.window.setup.recipe_preview.setText("\n\n".join(lines))
        self.window.start_recipe_btn.setEnabled(True)
        self.status("Recipe ready. Review its steps, then start when ready.")

    def start(self, mode):
        if self.window.running:
            return
        try:
            measurement, gate = self.window.settings()
            load_failure_flows(self.config)
            stages = (
                load_recipe(self.recipe_path, self.config, gate)
                if mode == "recipe"
                else None
            )
            for profile in [s.gate for s in stages] if stages else [gate]:
                HardwareFactory(self.config).validate(profile)
            worker = ExperimentWorker(self.config, measurement, gate, stages)
            if mode == "manual":
                worker.update_manual_setpoints(
                    self.window.setup.shutter_checkbox.isChecked(), self.flow_targets()
                )
        except Exception as exc:
            self.error(str(exc))
            return
        self.worker = worker
        self.window.reset_readings()
        self.window.running = True
        self.window.setup.set_running(True)
        self.window.setup.gate_group.setEnabled(False)
        self.window.start_manual_btn.setEnabled(False)
        self.window.start_recipe_btn.setEnabled(False)
        self.window.setup.load_recipe_btn.setEnabled(False)
        self.window.stop_btn.setEnabled(True)
        self.window.apply_manual_btn.setEnabled(mode == "manual")
        self.window.setup.control_tabs.setTabEnabled(0, mode == "manual")
        self.window.setup.control_tabs.setTabEnabled(1, mode == "recipe")
        worker.data_sig.connect(self.update_data)
        worker.status_sig.connect(self.status)
        worker.error_sig.connect(self.error)
        worker.finished.connect(self.finished)
        self.window.refresh_summary()
        self.window.show_monitor()
        self.status("Starting · preparing instruments")
        worker.start()

    def flow_targets(self):
        return {
            ch: widget.value() for ch, widget in self.window.setup.flow_inputs.items()
        }

    def apply_manual(self):
        if self.worker and self.window.running:
            try:
                self.worker.update_manual_setpoints(
                    self.window.setup.shutter_checkbox.isChecked(), self.flow_targets()
                )
                self.status("Gas changes queued · applied after the current sweep")
            except Exception as exc:
                self.error(str(exc))

    def update_data(self, data):
        self.window.show_reading(data)

    def apply_range(self):
        if self.worker and self.window.running:
            try:
                self.worker.engine.update_resistance_range(
                    self.window.setup.auto_range.isChecked(),
                    self.window.setup.manual_range.value(),
                )
                self.status("Resistance range queued · applies before the next scan")
            except Exception as exc:
                self.error(str(exc))

    def status(self, text):
        self.window.status_label.setText(text)
        state = "complete" if text in ("Complete", "Stopped") else "ready"
        self.window.status_label.setProperty("state", state)
        refresh_style(self.window.status_label)
        self.log(text)

    def error(self, text):
        self.window.status_label.setText(f"Error: {text}")
        self.window.status_label.setProperty("state", "error")
        refresh_style(self.window.status_label)
        self.window.details_toggle.setChecked(True)
        self.log(f"ERROR: {text}")

    def stop(self):
        if self.worker and self.window.running:
            self.worker.stop()
            self.window.stop_btn.setEnabled(False)
            self.status("Stopping sources and applying failure gas profile…")

    def close_requested(self):
        self.closing = True
        self.stop()

    def finished(self):
        worker = self.worker
        self.window.running = False
        self.window.setup.set_running(False)
        self.window.setup.gate_group.setEnabled(True)
        self.window.start_manual_btn.setEnabled(True)
        self.window.start_recipe_btn.setEnabled(bool(self.recipe_path))
        self.window.setup.load_recipe_btn.setEnabled(True)
        self.window.stop_btn.setEnabled(False)
        self.window.apply_manual_btn.setEnabled(False)
        for index in (0, 1):
            self.window.setup.control_tabs.setTabEnabled(index, True)
        if worker.engine.log_path:
            self.log(f"CSV: {worker.engine.log_path}")
            self.window.saved_file.setText("CSV saved · see Session details")
            self.window.saved_file.setToolTip(worker.engine.log_path)
        if worker.engine.errors:
            self.error(worker.engine.errors[-1])
        self.worker = None
        self.window.refresh_summary()
        worker.deleteLater()
        if self.closing:
            self.close_log()
            QTimer.singleShot(0, self.window.close)
