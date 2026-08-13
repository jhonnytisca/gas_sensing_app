import yaml
from pathlib import Path

from .models import(
    AppConfig,
    HardwareConfig,
    KeithleyConfig
    )

    
class Config:

    def __init__(self, path: str | Path):
        path = Path(path)

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.hardware = HardwareConfig(
            use_mock=data["hardware"]["use_mock"],
            keithley=KeithleyConfig(
                **data["hardware"]["keithley"]
            ),
        )