import re
from pathlib import Path

import yaml

from .models import (
    AppConfig,
    ConsoleLogConfig,
    DataLogConfig,
    GateSettings,
    HardwareConfig,
    Keithley2400Config,
    Keithley2700Config,
    LoggingConfig,
    MeasurementSettings,
    MFCControllerConfig,
    ShutterConfig,
)
from .validation import finite, flows


class Config:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()

    def load(self) -> AppConfig:
        with self.path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a YAML mapping")
        hw = data.get("hardware", {})
        mock = hw.get("use_mock", True)
        if not isinstance(mock, bool):
            raise ValueError("hardware.use_mock must be true or false")
        mfc = MFCControllerConfig(**hw.get("mfc_controller", {}))
        mfc.range_sccm = {
            int(k): finite(v, f"range {k}", 1e-9) for k, v in mfc.range_sccm.items()
        }
        if not mfc.range_sccm or not set(mfc.range_sccm) <= {1, 2, 3, 4}:
            raise ValueError("ROD-4 supports gas channels 1–4")
        mfc.gas_names = {
            ch: str(mfc.gas_names.get(ch, mfc.gas_names.get(str(ch), f"mfc{ch}")))
            for ch in mfc.range_sccm
        }
        if any(
            not re.fullmatch(r"[A-Za-z0-9_]+", name) for name in mfc.gas_names.values()
        ):
            raise ValueError("Gas names must use letters, digits and underscores")
        k2400 = Keithley2400Config(**hw.get("keithley_2400", {}))
        settings = dict(data.get("measurement", {}))
        settings.setdefault("wire_mode", 4 if k2400.four_wire else 2)
        settings.setdefault("auto_range", k2400.auto_range)
        settings.setdefault("manual_range", k2400.manual_range)
        logging = data.get("logging", {})
        result = AppConfig(
            hardware=HardwareConfig(
                mock,
                k2400,
                ShutterConfig(**hw.get("shutter", {})),
                mfc,
                Keithley2700Config(**hw.get("keithley_2700", {})),
            ),
            logging=LoggingConfig(
                DataLogConfig(**logging.get("data_log", {})),
                ConsoleLogConfig(**logging.get("console_log", {})),
            ),
            measurement=MeasurementSettings(**settings),
            gate=GateSettings(**data.get("gate", {})),
            safety_file=data.get("safety_file", "failure_gases.yaml"),
            base_dir=str(self.path.parent),
        )
        result.measurement.validate()
        result.gate.points()
        if (
            Path(result.logging.data_log.filename_prefix).name
            != result.logging.data_log.filename_prefix
        ):
            raise ValueError("CSV prefix must be a filename, not a path")
        return result


def load_failure_flows(config):
    path = Path(config.base_dir) / config.safety_file
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict) or "mfc_flows" not in data:
        raise ValueError("Failure gas configuration requires mfc_flows")
    return flows(data["mfc_flows"], config.hardware.mfc_controller.range_sccm)
