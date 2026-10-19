"""Qt bridge only. The instrument lifecycle lives in ExperimentEngine."""

from PyQt6.QtCore import QThread, pyqtSignal

from .engine import ExperimentEngine


class ExperimentWorker(QThread):
    data_sig = pyqtSignal(dict)
    status_sig = pyqtSignal(str)
    error_sig = pyqtSignal(str)

    def __init__(self, config, measurement, gate, stages=None, parent=None):
        super().__init__(parent)
        self.engine = ExperimentEngine(
            config,
            measurement,
            gate,
            stages,
            on_data=self.data_sig.emit,
            on_status=self.status_sig.emit,
            on_error=self.error_sig.emit,
        )

    def update_manual_setpoints(self, shutter_open, flows):
        self.engine.update_manual(shutter_open, flows)

    def stop(self):
        self.engine.stop()

    def run(self):
        self.engine.run()
