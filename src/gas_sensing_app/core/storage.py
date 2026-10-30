"""Append-only experiment storage, committed after every sensor reading."""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class MeasurementCSV:
    def __init__(self, folder, prefix, channels):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        self.path = folder / f"{prefix}_{stamp}_{uuid4().hex[:8]}.csv"
        self.fields = [
            "timestamp",
            "elapsed_s",
            "scan_id",
            "recipe_step",
            "sensor_id",
            "sense_channel",
            "resistance_ohm",
            "voltage_V",
            "current_A",
            "measurement_status",
            "resistance_range_mode",
            "resistance_range_requested_ohm",
            "resistance_range_actual_ohm",
            "gate_setpoint_V",
            "gate_voltage_V",
            "gate_status",
            "shutter_open",
        ]
        for channel, name in channels.items():
            self.fields.extend(
                [
                    f"gas_{channel}_{name}_setpoint_sccm",
                    f"gas_{channel}_{name}_actual_sccm",
                ]
            )
        self.file = self.path.open("x", newline="", encoding="utf-8")
        try:
            self.writer = csv.DictWriter(self.file, self.fields)
            self.writer.writeheader()
            self.sync()
        except BaseException:
            self.file.close()
            raise

    def sync(self):
        self.file.flush()
        os.fsync(self.file.fileno())

    def write_metadata(self, metadata):
        self.metadata_path = self.path.with_suffix(".metadata.json")
        with self.metadata_path.open("x", encoding="utf-8") as stream:
            json.dump(
                dict(schema_version=2, data_file=self.path.name, **metadata),
                stream,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def write(self, row):
        self.writer.writerow(row)
        self.sync()

    def close(self):
        self.file.close()
