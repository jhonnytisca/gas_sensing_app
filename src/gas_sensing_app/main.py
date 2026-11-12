"""Application composition root; no hardware I/O before the user starts a run."""

import argparse
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from gas_sensing_app.config.workspace import startup_config

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def main():
    parser = argparse.ArgumentParser(description="Gas sensor acquisition")
    parser.add_argument("--config", help="Load an existing configuration YAML")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("GasSensingApp")
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "icon.png")))
    try:
        config = startup_config(args.config)
        from gas_sensing_app.config.connections import load_local_connections

        try:
            load_local_connections(config)
        except Exception as exc:
            QMessageBox.warning(
                None,
                "Local device connections",
                f"Local connections could not be loaded: {exc}\n"
                "Startup YAML addresses will be used. Open Devices to correct them.",
            )
        # Delay GUI imports until QApplication exists (font/theme setup).
        from gas_sensing_app.controllers.dashboard_controller import DashboardController
        from gas_sensing_app.gui.dashboard import Dashboard

        window = Dashboard(config)
        controller = DashboardController(window, config)
        app.aboutToQuit.connect(controller.close_log)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "Startup error", str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
