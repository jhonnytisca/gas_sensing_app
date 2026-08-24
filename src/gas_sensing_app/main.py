import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from gas_sensing_app.config.config import Config
from gas_sensing_app.controllers.dashboard_controller import DashboardController
from gas_sensing_app.gui.dashboard import Dashboard

PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
ROOT_DIR = Path.cwd().expanduser().resolve()


def main():
    app = QApplication(sys.argv)

    # Define explicit app signatures (Critical for Linux taskbar linking)
    app.setApplicationName("GasSensingApp")
    app.setApplicationDisplayName("Gas Sensing Dashboard")
    app.setDesktopFileName("Gas_Sensing_App.desktop")

    # Resolve path to the icon relative to main.py
    icon_path = ASSETS_DIR / "icon.png"

    # Apply the icon to the entire OS process hierarchy
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    else:
        print(f"[WARNING]: Global icon asset not found at: {icon_path}")

    # Load configurations
    # TODO retrieve default configs if file not found
    config_path = ROOT_DIR / "config.yaml"
    config = Config(config_path).load()

    # Set main window and main controller
    window = Dashboard(logging_config=config.logging)
    controller = DashboardController(window, config_path=config_path)  # noqa: F841

    # Show window
    window.show()

    # System exit
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
