from dataclasses import dataclass

@dataclass
class KeithleyConfig:
    port: str
    auto_range: bool
    manual_range: float
    four_wire: bool

@dataclass
class HardwareConfig:
    use_mock: bool
    keithley: KeithleyConfig

@dataclass
class AppConfig:
    hadware: HardwareConfig