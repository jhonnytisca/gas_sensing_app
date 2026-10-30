"""Standalone results previewer entry point; never opens instrument connections."""

import argparse
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess


def launch_previewer(config):
    folder = (Path(config.base_dir) / config.logging.data_log.folder).resolve()
    started, _ = QProcess.startDetached(
        sys.executable,
        ["-m", "gas_sensing_app.preview_results", "--folder", str(folder)],
        str(Path(config.base_dir).resolve()),
    )
    if not started:
        raise RuntimeError("Could not start the results previewer")


def main():
    parser = argparse.ArgumentParser(
        description="Browse experiment CSVs without connecting instruments"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Config whose data folder is the startup default",
    )
    parser.add_argument("--folder", help="Override the default results folder")
    args = parser.parse_args()
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from gas_sensing_app.gui.results_previewer import ResultsPreviewer
    from gas_sensing_app.results import default_data_folder

    app = QApplication(sys.argv[:1])
    app.setApplicationName("GasSensingResults")
    try:
        folder = (
            Path(args.folder).expanduser().resolve()
            if args.folder
            else default_data_folder(args.config)
        )
        window = ResultsPreviewer(folder)
    except Exception as exc:
        QMessageBox.critical(None, "Results previewer", str(exc))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
