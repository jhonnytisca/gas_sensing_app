"""Shared configuration models for UI, experiment engine and drivers."""

from dataclasses import dataclass, field


@dataclass
class Keithley2400Config:
    port: str = "GPIB0::24::INSTR"
    auto_range: bool = True
    manual_range: float = 200000.0
    four_wire: bool = False


@dataclass
class Keithley2700Config:
    port: str = "GPIB0::16::INSTR"


@dataclass
class ShutterConfig:
    port: str = "MOCK"
    baud_rate: int = 115200
    open_angle: int = 90
    closed_angle: int = 0
    enabled: bool = True


@dataclass
class MFCControllerConfig:
    port: str = "MOCK"
    range_sccm: dict[int, float] = field(
        default_factory=lambda: {1: 1000, 2: 1000, 3: 200, 4: 200}
    )
    gas_names: dict[int, str] = field(
        default_factory=lambda: {
            1: "dry_air",
            2: "wet_air",
            3: "analyte_1",
            4: "analyte_2",
        }
    )


@dataclass
class HardwareConfig:
    use_mock: bool
    keithley_2400: Keithley2400Config
    shutter: ShutterConfig
    mfc_controller: MFCControllerConfig
    keithley_2700: Keithley2700Config = field(default_factory=Keithley2700Config)


@dataclass
class DataLogConfig:
    folder: str = "data"
    filename_prefix: str = "gas_experiment"


@dataclass
class ConsoleLogConfig:
    enabled: bool = True
    folder: str = "console_logs"
    filename_prefix: str = "system_console"


@dataclass
class LoggingConfig:
    data_log: DataLogConfig = field(default_factory=DataLogConfig)
    console_log: ConsoleLogConfig = field(default_factory=ConsoleLogConfig)


@dataclass
class MeasurementSettings:
    instrument: str = "2400"
    mode: str = "resistance"
    wire_mode: int = 2
    slot: int = 1
    first_channel: int = 1
    last_channel: int = 1
    bias_voltage: float = 1.0
    compliance: float = 0.01
    interval_s: float = 1.0
    auto_range: bool = True
    manual_range: float = 200000.0

    @property
    def channels(self):
        if self.instrument == "2400":
            return [None]
        return [
            self.slot * 100 + ch
            for ch in range(self.first_channel, self.last_channel + 1)
        ]

    def validate(self):
        from .validation import finite

        if self.instrument not in ("2400", "2700") or self.wire_mode not in (2, 4):
            raise ValueError("Select a supported instrument and 2 or 4 terminals")
        modes = (
            ("resistance", "constant_voltage")
            if self.instrument == "2400"
            else ("resistance", "voltage")
        )
        if self.mode not in modes:
            raise ValueError(
                f"Mode {self.mode!r} is not supported by {self.instrument}"
            )
        if not isinstance(self.auto_range, bool):
            raise ValueError("auto_range must be a boolean")
        for key in ("wire_mode", "slot", "first_channel", "last_channel"):
            if type(getattr(self, key)) is not int:
                raise ValueError(f"{key} must be an integer")
        if self.instrument == "2700":
            limit = 10 if self.wire_mode == 4 else 20
            if (
                self.slot not in (1, 2)
                or not 1 <= self.first_channel <= self.last_channel <= limit
            ):
                raise ValueError(f"7706 requires slot 1/2 and channels 1–{limit}")
            if self.mode == "voltage" and self.wire_mode == 4:
                raise ValueError(
                    "2700 voltage uses two terminals; "
                    "four-terminal mode is for resistance"
                )
        finite(self.bias_voltage, "bias_voltage", -200, 200)
        finite(self.compliance, "compliance", 1e-9, 1.05)
        finite(self.interval_s, "interval_s", 0.01, 86400)
        finite(self.manual_range, "manual_range", 1e-9, 1e12)


@dataclass
class GateSettings:
    enabled: bool = False
    mode: str = "fixed"
    voltage: float = 0.0
    start: float = 0.0
    stop: float = 1.0
    step: float = 0.1
    dwell_s: float = 1.0
    current_limit: float = 0.001
    max_voltage: float = 65.0

    def points(self):
        from .validation import finite

        if not isinstance(self.enabled, bool):
            raise ValueError("gate.enabled must be a boolean")
        if self.mode not in ("fixed", "sweep"):
            raise ValueError("Gate mode must be fixed or sweep")
        finite(self.max_voltage, "gate.max_voltage", 0, 65)
        finite(self.current_limit, "gate.current_limit", 1e-9, 3)
        finite(self.dwell_s, "gate.dwell_s", 0.01, 86400)
        for key in ("voltage", "start", "stop"):
            finite(getattr(self, key), f"gate.{key}", 0, self.max_voltage)
        finite(self.step, "gate.step", 1e-9, 65)
        if not self.enabled:
            return [None]
        if self.mode == "fixed":
            return [self.voltage]
        distance = abs(self.stop - self.start)
        count = int(distance / self.step + 1e-10)
        if count > 10000:
            raise ValueError("A gate sweep may contain at most 10001 points")
        direction = 1 if self.stop >= self.start else -1
        points = [self.start + direction * i * self.step for i in range(count + 1)]
        if abs(points[-1] - self.stop) > 1e-9:
            points.append(self.stop)
        return points


@dataclass
class AppConfig:
    hardware: HardwareConfig
    logging: LoggingConfig
    measurement: MeasurementSettings = field(default_factory=MeasurementSettings)
    gate: GateSettings = field(default_factory=GateSettings)
    safety_file: str = "failure_gases.yaml"
    base_dir: str = "."
