"""Append-only experiment storage, committed after every sensor reading."""

import csv
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
            "step",
            "device",
            "slot",
            "channel",
            "sense_channel",
            "wire_mode",
            "resistance_ohm",
            "voltage_V",
            "current_A",
            "measurement_status",
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

    def write(self, row):
        self.writer.writerow(row)
        self.sync()

    def close(self):
        self.file.close()
