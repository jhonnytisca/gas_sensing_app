from dataclasses import dataclass


# Hardware configurations
@dataclass
class Keithley2400Config:
    port: str
    auto_range: bool
    manual_range: float
    four_wire: bool


@dataclass
class ShutterConfig:
    port: str
    baud_rate: int
    open_angle: int
    closed_angle: int


@dataclass
class MFCControllerConfig:
    port: str
    range_sccm: dict[int, float]


@dataclass
class HardwareConfig:
    use_mock: bool
    keithley_2400: Keithley2400Config
    shutter: ShutterConfig
    mfc_controller: MFCControllerConfig


# Logging configurations
@dataclass
class DataLogConfig:
    folder: str
    filename_prefix: str


@dataclass
class ConsoleLogConfig:
    enabled: bool
    folder: str
    filename_prefix: str


@dataclass
class LoggingConfig:
    data_log: DataLogConfig
    console_log: ConsoleLogConfig


# App configurations
@dataclass
class AppConfig:
    hardware: HardwareConfig
    logging: LoggingConfig
