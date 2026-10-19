"""Construct only the devices required by this run; imports stay lazy."""


class HardwareFactory:
    def __init__(self, config, gate_transport_factory=None):
        self.config = config
        self.gate_transport_factory = gate_transport_factory

    def validate(self, gate):
        if (
            gate.enabled
            and not self.config.hardware.use_mock
            and self.gate_transport_factory is None
        ):
            raise ValueError(
                "EA-PS transport is not configured. Use Mock or disable gate "
                "until the physical interface is integrated."
            )

    def meter(self, settings):
        hw = self.config.hardware
        if hw.use_mock:
            from .mock_drivers import MockKeithley2400, MockKeithley2700

            cls = (
                MockKeithley2400 if settings.instrument == "2400" else MockKeithley2700
            )
        elif settings.instrument == "2400":
            from .keithley_2400 import Keithley2400 as cls
        else:
            from .keithley_2700 import Keithley2700 as cls
        cfg = hw.keithley_2400 if settings.instrument == "2400" else hw.keithley_2700
        if not hw.use_mock and settings.instrument == "2700":
            return cls(
                cfg.port, baud_rate=cfg.baud_rate, read_termination=cfg.read_termination
            )
        return cls(cfg.port)

    def mfc(self):
        cfg = self.config.hardware.mfc_controller
        if self.config.hardware.use_mock:
            from .mock_drivers import MockAeraMFCManager as cls
        else:
            from .aera_mfc import AeraMFCManager as cls
        return cls(cfg.port, ranges=cfg.range_sccm)

    def shutter(self):
        cfg = self.config.hardware.shutter
        if not cfg.enabled:
            return None
        if self.config.hardware.use_mock:
            from .mock_drivers import MockShutterController as cls
        else:
            from .shutter import ShutterController as cls
        return cls(
            cfg.port,
            cfg.baud_rate,
            open_angle=cfg.open_angle,
            closed_angle=cfg.closed_angle,
        )

    def gate(self):
        if self.config.hardware.use_mock:
            from .mock_drivers import MockGateSupply

            return MockGateSupply()
        from .gate_supply import EAPS3065

        return EAPS3065(self.gate_transport_factory())
