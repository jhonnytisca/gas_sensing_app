from pathlib import Path

import yaml

from .models import (
    AppConfig,
    ConsoleLogConfig,
    DataLogConfig,
    HardwareConfig,
    Keithley2400Config,
    LoggingConfig,
    MFCControllerConfig,
    ShutterConfig,
)


class Config:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> AppConfig:
        data = self._read_yaml()

        return AppConfig(
            hardware=self._load_hardware(data["hardware"]),
            logging=self._load_logging(data["logging"]),
        )

    def _read_yaml(self) -> dict:
        with self.path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_hardware(self, data: dict) -> HardwareConfig:
        return HardwareConfig(
            use_mock=data["use_mock"],
            keithley_2400=Keithley2400Config(**data["keithley_2400"]),
            shutter=ShutterConfig(**data["shutter"]),
            mfc_controller=MFCControllerConfig(**data["mfc_controller"]),
        )

    def _load_logging(self, data: dict) -> LoggingConfig:
        return LoggingConfig(
            data_log=DataLogConfig(**data["data_log"]),
            console_log=ConsoleLogConfig(**data["console_log"]),
        )
