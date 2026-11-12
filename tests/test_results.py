import csv
import json
from types import SimpleNamespace

import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

from gas_sensing_app.gui.results_previewer import ResultsPreviewer
from gas_sensing_app.preview_results import launch_previewer
from gas_sensing_app.results import (
    default_data_folder,
    display_bounds,
    list_csv_files,
    load_result,
    merge_files,
)


def write_result(path, old=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    sensor = "device" if old else "sensor_id"
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "elapsed_s",
                sensor,
                "resistance_ohm",
                "voltage_V",
                "current_A",
                "gas_2_air_setpoint_sccm",
                "gas_2_air_actual_sccm",
                "scan_id",
            ]
        )
        for i in range(200):
            writer.writerow(
                [
                    i,
                    "101" if i % 2 == 0 else "103",
                    5000000 if i % 2 == 0 else "",
                    "",
                    "",
                    200,
                    80000 if i == 100 else 2000,
                    i // 2 + 1,
                ]
            )
    return path


@pytest.mark.parametrize("old", [True, False])
def test_load_formats_preserves_flow_when_resistance_missing(tmp_path, old):
    path = write_result(tmp_path / "experiment.csv", old)
    result = load_result(path)
    assert result.sensor_ids == ["101", "103"]
    assert np.isnan(result.values["resistance_ohm"][1])
    assert result.values["gas_2_air_actual_sccm"][1] == 2000
    assert len(result.time_s) == 200
    assert len(result.scan_ids) == 100


def test_metadata_and_invalid_rows(tmp_path):
    path = tmp_path / "result.csv"
    path.write_text(
        "elapsed_s,sensor_id,resistance_ohm\n0,101,9.9e37\nbad,101,2\n2,101,3\n3,101"
    )
    sidecar = path.with_suffix(".metadata.json")
    sidecar.write_text(
        json.dumps({"data_file": path.name, "measurement_initial": {"wire_mode": 2}})
    )
    result = load_result(path)
    assert len(result.time_s) == 2
    assert np.isnan(result.values["resistance_ohm"][0])
    assert result.metadata["measurement_initial"]["wire_mode"] == 2
    assert "Skipped 2" in result.warnings[0]
    sidecar.write_text('{"data_file": "different.csv"}')
    assert load_result(path).metadata is None
    path.write_text("elapsed_s,sensor_id,resistance_ohm\n")
    assert not len(load_result(path).time_s)
    path.write_text("other,column\n1,2\n")
    with pytest.raises(ValueError, match="elapsed time"):
        load_result(path)


def test_spike_resistant_bounds_preserve_short_setpoints_and_samples():
    values = np.full(200, 200.0)
    values[-1] = 8000
    lo, hi, outside = display_bounds([(values, False)])
    assert lo < 200 < hi < 8000
    assert outside == 1
    assert values[-1] == 8000
    assert display_bounds([(values, False)], robust=False)[1] > 8000
    assert display_bounds([(values, True)])[1] > 8000
    assert display_bounds([(np.array([1, 1000]), False)])[1] > 1000


def test_default_folder_and_replace_add_do_not_modify_sources(tmp_path):
    config = tmp_path / "workspace/settings/config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("logging:\n  data_log:\n    folder: experiments\n")
    folder = default_data_folder(config)
    assert folder == tmp_path / "workspace/experiments"
    one = write_result(folder / "one.csv")
    two = write_result(folder / "nested" / "two.csv")
    assert list_csv_files(folder) == [one]
    assert set(list_csv_files(folder, recursive=True)) == {one, two}
    assert merge_files([one], [two]) == [two]
    assert merge_files([one], [two, one], replace=False) == [one, two]
    assert one.exists() and two.exists()


def test_previewer_selection_label_zoom_export_and_lists(qtbot, tmp_path):
    first = write_result(tmp_path / "first" / "one.csv", old=True)
    second = write_result(tmp_path / "second" / "two.csv")
    before = first.read_bytes()
    window = ResultsPreviewer(first.parent)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.result is not None, timeout=5000)
    assert window.list_mode.currentIndex() == 0
    assert not hasattr(window, "correction")
    assert window.annotation.text() == ""
    assert set(window.plots) == {"resistance_ohm", "flows"}
    assert window.plots["flows"].viewRange()[1][1] < 80000
    original = window.result.values["gas_2_air_actual_sccm"].copy()
    window.annotation.setText("After cleaning <repeat 2>")
    assert "After cleaning &lt;repeat 2&gt;" in window.export_note.text
    setpoint, reported = window.curves["flows"]
    assert setpoint[1][0] == 200
    assert reported[1][0] == 2000
    assert np.array_equal(window.result.values["gas_2_air_actual_sccm"], original)
    window.full_view()
    assert window.plots["flows"].viewRange()[1][1] > 80000
    window.robust.setChecked(True)
    assert window.plots["flows"].viewRange()[1][1] < 80000
    # Selecting a sensor with unavailable R must still show its gas measurements.
    window.sensors.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert not window.curves["resistance_ohm"]
    assert len(window.curves["flows"][0][0]) == 100
    window.signal_buttons["resistance_ohm"].click()
    assert set(window.plots) == {"flows"}
    output = tmp_path / "preview.png"
    window.export_png(output)
    assert QImage(str(output)).width() == 1800
    assert first.read_bytes() == before
    window.open_folder(second.parent, replace=False)
    qtbot.waitUntil(lambda: window.result is not None, timeout=5000)
    assert window.paths == [first, second]
    window.open_folder(second.parent)
    qtbot.waitUntil(
        lambda: window.result is not None and window.result.path == second, timeout=5000
    )
    assert window.paths == [second]
    assert not hasattr(window, "correction")
    assert window.annotation.text() == ""
    assert window.default_folder == first.parent
    # A late background response must never overwrite the newer selection.
    window.loaded(window.load_token - 1, load_result(first), "")
    assert window.result.path == second


def test_launch_is_separate_process_with_actual_save_folder(monkeypatch, tmp_path):
    from gas_sensing_app import preview_results

    calls = []
    monkeypatch.setattr(
        preview_results.QProcess,
        "startDetached",
        lambda *args: (calls.append(args) or True, 123),
    )
    config = SimpleNamespace(
        base_dir=str(tmp_path / "workspace/settings"),
        workspace_dir=str(tmp_path / "workspace"),
        logging=SimpleNamespace(data_log=SimpleNamespace(folder="experiments")),
    )
    launch_previewer(config)
    assert calls[0][1] == [
        "-m",
        "gas_sensing_app.preview_results",
        "--folder",
        str(tmp_path / "workspace/experiments"),
    ]
    assert calls[0][2] == str(tmp_path / "workspace")


def test_identification_visible_without_json_dialog(qtbot, tmp_path):
    path = write_result(tmp_path / "sample" / "experiment" / "measurement.csv")
    path.with_suffix(".metadata.json").write_text(
        json.dumps(
            {
                "data_file": path.name,
                "sample_name": "SiGeI_20210310c",
                "device": "102,103,106",
                "experiment_name": "NO2",
                "description": "Repeat after cleaning",
                "session_state": "stopped",
                "measurement_initial": {
                    "mode": "constant_voltage",
                    "bias_voltage": 3.3,
                    "compliance": 1e-5,
                    "interval_s": 1.0,
                },
            }
        )
    )
    window = ResultsPreviewer(tmp_path)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: window.result is not None, timeout=5000)
    summary = window.experiment_summary.text()
    for value in (
        "SiGeI_20210310c",
        "102,103,106",
        "NO2",
        "Repeat after cleaning",
        "stopped",
        "3.3V",
    ):
        assert value in summary
    assert window.metadata_button.text() == "Full JSON"
    assert window.recursive.isChecked()
