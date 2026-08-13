import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from src.gas_sensing_app.gui.dashboard import Dashboard
from src.gas_sensing_app.controllers.dashboard_controller import DashboardController

ASSETS_DIR = Path(__file__).parent / "src" / "gas_sensing_app" / "assets"

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
        
    # Set main window and main controller
    window = Dashboard()
    controller = DashboardController(window)
    
    # Show window
    window.show()
    
    # System exit
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
