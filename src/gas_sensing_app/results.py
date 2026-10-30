"""Read-only result loading and display ranges, independent of instruments and Qt."""

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

ELECTRICAL = {
    "resistance_ohm": ("Resistance", "Ω"),
    "voltage_V": ("Voltage", "V"),
    "current_A": ("Current", "A"),
}
GAS_COLUMN = re.compile(r"gas_(\d+)_(.+)_(setpoint|actual)_sccm$")


@dataclass
class ResultData:
    path: Path
    time_s: np.ndarray
    sensors: np.ndarray
    values: dict
    gases: dict
    metadata: dict | None
    warnings: list = field(default_factory=list)
    scan_ids: set = field(default_factory=set)

    @property
    def sensor_ids(self):
        return list(dict.fromkeys(self.sensors.tolist()))

    def flow_divisors(self):
        ranges = (
            (self.metadata or {})
            .get("hardware", {})
            .get("mfc_controller", {})
            .get("range_sccm", {})
        )
        defaults = {1: 1000, 2: 1000, 3: 200, 4: 200}
        result = {}
        for channel in self.gases:
            value = ranges.get(str(channel), defaults.get(channel, 100))
            try:
                value = float(value) / 100
                if not math.isfinite(value) or value <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                value = 1
            result[channel] = value
        return result


def default_data_folder(config_path):
    """Read only the save-folder setting; no instrument validation or config writes."""
    config_path = Path(config_path).expanduser().resolve()
    if not config_path.exists():
        return config_path.parent / "data"
    with config_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a YAML mapping")
    folder = config.get("logging", {}).get("data_log", {}).get("folder", "data")
    return (config_path.parent / Path(folder).expanduser()).resolve()


def list_csv_files(folder, recursive=False):
    folder = Path(folder).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")
    paths = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(
        (p for p in paths if p.is_file() and p.suffix.lower() == ".csv"),
        key=lambda p: (p.name, str(p)),
        reverse=True,
    )


def merge_files(existing, incoming, replace=True):
    """Replace/add the list in memory, never the source files."""
    paths = [] if replace else list(existing)
    return list(dict.fromkeys(Path(p).resolve() for p in [*paths, *incoming]))


def read_metadata(path, warnings):
    metadata = None
    sidecar = path.with_suffix(".metadata.json")
    if sidecar.exists():
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("expected a JSON object")
            if metadata.get("data_file", path.name) != path.name:
                raise ValueError("data_file does not match this CSV")
        except (OSError, ValueError) as exc:
            metadata = None
            warnings.append(f"Metadata could not be used: {exc}")
    return metadata


def number(value):
    if value is None or not value.strip():
        return math.nan
    try:
        value = float(value)
        if math.isfinite(value) and abs(value) < 9e36:
            return value
    except ValueError:
        pass
    return math.nan


def read_columns(fields):
    columns = {key: key for key in ELECTRICAL if key in fields}
    if "Resistance" in fields and "resistance_ohm" not in columns:
        columns["resistance_ohm"] = "Resistance"
    gases = {}
    for key in fields:
        match = GAS_COLUMN.fullmatch(key)
        if match:
            channel, name, kind = match.groups()
            gases.setdefault(int(channel), {"name": name})[kind] = key
            columns[key] = key
        elif re.fullmatch(r"MFC[1-4]", key):
            gases[int(key[-1])] = {"name": key, "actual": key}
            columns[key] = key
    if not columns:
        raise ValueError("No supported electrical or gas columns found")
    return columns, gases


def load_result(path):
    path = Path(path).resolve()
    warnings = []
    metadata = read_metadata(path, warnings)
    times, sensors, scan_ids = [], [], set()
    skipped = 0

    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        time_key = "elapsed_s" if "elapsed_s" in fields else "Elapsed_Seconds"
        if time_key not in fields:
            raise ValueError("Not a supported experiment CSV: elapsed time is missing")
        columns, gases = read_columns(fields)
        values = {key: [] for key in columns}
        for row in reader:
            time_s = number(row.get(time_key))
            # A CSV still being written can end in an incomplete final row.
            if not math.isfinite(time_s) or None in row or None in row.values():
                skipped += 1
                continue
            times.append(time_s)
            sensors.append(row.get("sensor_id") or row.get("device") or "single")
            if row.get("scan_id"):
                scan_ids.add(row["scan_id"])
            for key, source in columns.items():
                values[key].append(number(row.get(source)))
    if time_key == "Elapsed_Seconds":
        warnings.append("Early CSV format: verify the stored Resistance/MFC units.")
    if skipped:
        warnings.append(
            f"Skipped {skipped} malformed rows or rows without elapsed time."
        )
    if not times:
        warnings.append("No readings yet (empty or header-only file).")
    order = np.argsort(times, kind="stable")
    return ResultData(
        path,
        np.asarray(times)[order],
        np.asarray(sensors, dtype=str)[order],
        {key: np.asarray(value)[order] for key, value in values.items()},
        gases,
        metadata,
        warnings,
        scan_ids,
    )


def display_bounds(series, robust=True):
    """Per-curve quantile fit: changes axes only; never filters stored samples.

    Each pair is (values, preserve_extremes). Setpoints always preserve extremes,
    keeping short requested gas pulses in view. Small series are shown in full.
    """
    bounds = []
    all_values = []
    for values, preserve_extremes in series:
        values = values[np.isfinite(values)]
        if not len(values):
            continue
        all_values.append(values)
        if robust and not preserve_extremes and len(values) >= 20:
            lo, hi = np.quantile(values, [0.01, 0.99])
        else:
            lo, hi = values.min(), values.max()
        bounds.append((lo, hi))
    if not bounds:
        return None
    lo, hi = min(b[0] for b in bounds), max(b[1] for b in bounds)
    padding = max((hi - lo) * 0.08, max(abs(lo), abs(hi)) * 0.01, 1e-12)
    lo, hi = lo - padding, hi + padding
    outside = sum(int(np.count_nonzero((v < lo) | (v > hi))) for v in all_values)
    return float(lo), float(hi), outside
