"""Single owner of run state, GUI actions and worker lifecycle."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QFileDialog

from gas_sensing_app.config.config import load_failure_flows
from gas_sensing_app.config.connections import (
    connection_problems,
    save_local_connections,
)
from gas_sensing_app.config.profiles import load_profile, save_profile
from gas_sensing_app.core.recipe import load_recipe
from gas_sensing_app.core.worker import ExperimentWorker
from gas_sensing_app.gui.connections_dialog import ConnectionsDialog
from gas_sensing_app.gui.styles.theme_manager import load_theme, refresh_style
from gas_sensing_app.hardware.factory import HardwareFactory


class DashboardController:
    def __init__(self, window, config):
        self.window, self.config = window, config
        self.worker = None
        self.recipe_path = None
        self.closing = False
        self.console_log = self.open_console_log(config)
        window.theme_selector.currentIndexChanged.connect(self.change_theme)
        self.bind_setup()
        window.load_config_btn.clicked.connect(self.select_configuration)
        window.save_config_btn.clicked.connect(self.save_configuration)
        window.connections_btn.clicked.connect(self.configure_devices)
        window.start_recipe_btn.clicked.connect(lambda: self.start("recipe"))
        window.start_manual_btn.clicked.connect(lambda: self.start("manual"))
        window.apply_manual_btn.clicked.connect(self.apply_manual)
        window.stop_btn.clicked.connect(self.stop)
        window.close_requested.connect(self.close_requested)
        window.destroyed.connect(self.close_log)
        if config.recipe_file:
            self.load_recipe_file(config.recipe_file)

    @staticmethod
    def open_console_log(config):
        console = config.logging.console_log
        if not console.enabled:
            return None
        folder = Path(config.base_dir) / console.folder
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        return (folder / f"{console.filename_prefix}_{stamp}.log").open(
            "x", encoding="utf-8"
        )

    def bind_setup(self):
        self.window.setup.load_recipe_btn.clicked.connect(self.select_recipe)
        self.window.setup.apply_range_btn.clicked.connect(self.apply_range)

    def select_configuration(self):
        if self.window.running:
            return
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "Load experiment configuration",
            self.config.base_dir,
            "YAML (*.yaml *.yml)",
        )
        if path:
            self.load_configuration_file(path)

    def load_configuration_file(self, path):
        if self.window.running:
            return False
        console_log = None
        try:
            config = load_profile(path, self.config)
            console_log = self.open_console_log(config)
            self.window.apply_configuration(config)
        except Exception as exc:
            if console_log:
                console_log.close()
            self.error(f"Configuration not loaded: {exc}")
            return False
        self.close_log()
        self.console_log = console_log
        self.config = config
        self.recipe_path = None
        self.window.start_recipe_btn.setEnabled(False)
        self.bind_setup()
        if config.recipe_file:
            self.load_recipe_file(config.recipe_file)
        self.status(
            f"Configuration loaded: {Path(path).name}. Review settings before starting."
        )
        if (
            connection_problems(config, config.measurement)
            and not self.configure_devices()
        ):
            self.status(
                "Configuration loaded. Assign required ports with Devices "
                "before starting."
            )
        return True

    def save_configuration(self):
        path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Save experiment configuration",
            self.config.base_dir,
            "YAML (*.yaml *.yml)",
        )
        if path:
            if Path(path).suffix.lower() not in (".yaml", ".yml"):
                path += ".yaml"
            self.save_configuration_file(path)

    def save_configuration_file(self, path):
        try:
            measurement, gate = self.window.settings()
            mode = (
                "recipe"
                if self.window.setup.control_tabs.currentIndex() == 1
                else "manual"
            )
            source = save_profile(
                path,
                replace(self.config, **self.window.sample_notes.values()),
                measurement,
                gate,
                self.flow_targets(),
                self.window.setup.shutter_checkbox.isChecked(),
                mode,
                self.recipe_path,
            )
        except Exception as exc:
            self.error(f"Configuration not saved: {exc}")
            return False
        self.config.configuration_source = source
        self.status(f"Configuration saved: {Path(path).name}")
        return True

    def configure_devices(self):
        if self.window.running:
            return False
        # Port setup should remain usable even if another form value is invalid.
        measurement = replace(
            self.config.measurement,
            instrument=self.window.setup.instrument.currentData(),
        )
        dialog = ConnectionsDialog(self.config, measurement, self.window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return False
        try:
            save_local_connections(dialog.config)
        except Exception as exc:
            self.error(f"Device connections not saved: {exc}")
            dialog.deleteLater()
            return False
        self.config.hardware = deepcopy(dialog.config.hardware)
        self.window.setup.shutter_checkbox.setEnabled(
            self.config.hardware.shutter.enabled
        )
        if not self.config.hardware.shutter.enabled:
            self.window.setup.shutter_checkbox.setChecked(False)
        self.window.refresh_mode_badge()
        self.window.setup.gate_changed()
        self.status("Device connections saved on this computer.")
        dialog.deleteLater()
        return True

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
        total_duration = sum(stage.estimated_duration for stage in stages)
        lines = [f"Estimated total duration: {total_duration / 60:.2f} min"]
        for index, stage in enumerate(stages, 1):
            total = sum(stage.flows.values())
            gate_text = stage.gate.mode if stage.gate.enabled else "off"
            flow_details = "\n      ".join(
                f"CH{ch} {self.config.hardware.mfc_controller.gas_names[ch]}: "
                f"{value:g} sccm"
                for ch, value in stage.flows.items()
            )
            lines.append(
                f"{index}. {stage.name} · at least {stage.duration:g} s\n"
                f"      {flow_details}\n"
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
            if connection_problems(self.config, measurement):
                if not self.configure_devices():
                    return
                problems = connection_problems(self.config, measurement)
                if problems:
                    raise ValueError("; ".join(problems))
            load_failure_flows(self.config)
            stages = (
                load_recipe(self.recipe_path, self.config, gate)
                if mode == "recipe"
                else None
            )
            for profile in [s.gate for s in stages] if stages else [gate]:
                HardwareFactory(self.config).validate(profile)
            run_config = replace(
                self.config,
                **self.window.sample_notes.values(),
                measurement=measurement,
                gate=gate,
                manual_flows=self.flow_targets(),
                manual_shutter_open=self.window.setup.shutter_checkbox.isChecked(),
                acquisition_mode=mode,
                recipe_file=self.recipe_path,
                configuration_source=dict(self.config.configuration_source),
            )
            worker = ExperimentWorker(run_config, measurement, gate, stages)
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
        self.window.load_config_btn.setEnabled(False)
        self.window.connections_btn.setEnabled(False)
        self.window.setup.set_running(True)
        self.window.sample_notes.set_running(True)
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
        self.window.load_config_btn.setEnabled(True)
        self.window.connections_btn.setEnabled(True)
        self.window.setup.set_running(False)
        self.window.sample_notes.set_running(False)
        self.window.setup.gate_group.setEnabled(True)
        self.window.start_manual_btn.setEnabled(True)
        self.window.start_recipe_btn.setEnabled(bool(self.recipe_path))
        self.window.setup.load_recipe_btn.setEnabled(True)
        self.window.stop_btn.setEnabled(False)
        self.window.apply_manual_btn.setEnabled(False)
        for index in (0, 1):
            self.window.setup.control_tabs.setTabEnabled(index, True)
        if worker.engine.log_path:
            from pathlib import Path

            original = Path(worker.engine.log_path)
            state = getattr(worker.engine.csv, "metadata", {}).get("session_state")
            suffix = (
                state
                if state in ("stopped", "failed")
                else (
                    "modified"
                    if getattr(worker.engine.csv, "metadata", {}).get(
                        "configuration_events"
                    )
                    else None
                )
            )
            if suffix:
                try:
                    target = original.parent.with_name(
                        original.parent.name + "__" + suffix
                    )
                    original.parent.rename(target)
                    worker.engine.log_path = target / original.name
                    worker.engine.csv.path = worker.engine.log_path
                    worker.engine.csv.metadata_path = (
                        worker.engine.log_path.with_suffix(".metadata.json")
                    )
                except OSError as exc:
                    self.log(f"Could not label session folder: {exc}")
            self.log(f"CSV: {worker.engine.log_path}")
            self.window.saved_file.setText('<a href="session-log">CSV saved</a>')
            self.window.saved_file.setToolTip(
                f"{worker.engine.log_path}\nOpen Session log for the full CSV path."
            )
            self.window.saved_file.show()
        if worker.engine.log_path:
            try:
                from gas_sensing_app.gui.plot_export import export_overview_isolated

                image = export_overview_isolated(worker.engine.log_path)
                if image:
                    self.log(f"Plot: {image}")
            except Exception as exc:
                self.log(f"Plot export failed; CSV preserved: {exc}")
        if worker.engine.errors:
            self.error(worker.engine.errors[-1])
        self.worker = None
        self.window.refresh_summary()
        worker.deleteLater()
        if self.closing:
            self.close_log()
            QTimer.singleShot(0, self.window.close)
