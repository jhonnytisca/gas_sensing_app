"""Export the same dark plots and experiment heading used by the results viewer."""


def export_overview(csv_path):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from gas_sensing_app.gui.results_previewer import ResultsPreviewer
    from gas_sensing_app.results import load_result

    result = load_result(csv_path)
    if not len(result.time_s):
        return None
    window = ResultsPreviewer(result.path.parent, autoload=False)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.resize(1700, 1150)
    window.show()
    QApplication.processEvents()
    window.loaded(window.load_token, result, "")
    QApplication.processEvents()
    window.fit_view()
    window.fit_timer.stop()
    output = result.path.parent / "plot.png"
    try:
        window.export_png(output)
    finally:
        window.close()
    return output


def export_overview_isolated(csv_path):
    """Keep temporary plotting objects and Qt export state out of the live GUI."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    output = Path(csv_path).parent / "plot.png"
    result = subprocess.run(
        [sys.executable, "-m", "gas_sensing_app.gui.plot_export", str(csv_path)],
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:] or "Image export failed")
    return output if output.exists() else None


if __name__ == "__main__":
    import sys

    from PyQt6.QtWidgets import QApplication

    app = QApplication([])
    export_overview(sys.argv[1])
