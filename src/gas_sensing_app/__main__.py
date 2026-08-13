# src/gas_sensing_app/__main__.py

import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

# Absolute application package calls
from gas_sensing_app.gui.dashboard import Dashboard

def main():
    # --- WINDOWS TASKBAR FIX ---
    if os.name == 'nt':
        import ctypes
        app_id = "nanochemistry.gassensing.dashboard.2026"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    # ---------------------------

    app = QApplication(sys.argv)
    
    # 1. Inject explicit app signatures (Crucial for macOS & Linux taskbar group-linking)
    app.setApplicationName("GasSensingApp")
    app.setApplicationDisplayName("Gas Sensing Dashboard")
    app.setDesktopFileName("Gas_Sensing_App.desktop")
    
    # 2. Resolve package asset paths relative to this module
    SCRIPT_DIR = Path(__file__).resolve().parent 
    ICON_PATH = SCRIPT_DIR / "assets" / "icon.png"  
    
    # 3. Apply the icon globally to the windowing system manager
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    else:
        print(f"[WARNING]: Package icon asset not found at: {ICON_PATH}")

    window = Dashboard()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()