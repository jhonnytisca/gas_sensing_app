"""Application composition root; no hardware I/O before the user starts a run."""

import argparse
import shutil
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from gas_sensing_app.config.config import Config

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def main():
    parser = argparse.ArgumentParser(description="Gas sensor acquisition")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("GasSensingApp")
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "icon.png")))
    try:
        path = Path(args.config).resolve()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ASSETS_DIR / "config.template.yaml", path)
        config = Config(path).load()
        failure_path = Path(config.base_dir) / config.safety_file
        if not failure_path.exists():
            failure_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ASSETS_DIR / "failure_gases.template.yaml", failure_path)
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
