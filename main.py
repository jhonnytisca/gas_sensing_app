import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from gas_sensing_app.gui.dashboard import Dashboard

import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from src.gas_sensing_app.gui.dashboard import Dashboard

def main():
    app = QApplication(sys.argv)
    
    # 1. Define explicit app signatures (Critical for Linux taskbar linking)
    app.setApplicationName("GasSensingApp")
    app.setApplicationDisplayName("Gas Sensing Dashboard")
    app.setDesktopFileName("Gas_Sensing_App.desktop")
    
    # 2. Resolve path to the icon relative to main.py
    root_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(root_dir, "src", "gas_sensing_app", "assets", "icon.png")
    
    # 3. Apply the icon to the entire OS process hierarchy
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        print(f"[WARNING]: Global icon asset not found at: {icon_path}")
        
    window = Dashboard()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
