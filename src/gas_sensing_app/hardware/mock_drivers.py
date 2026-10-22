"""Deterministic test instruments with the same public methods as real drivers."""

from gas_sensing_app.config.validation import finite
from gas_sensing_app.core.measurement import Reading


class MockKeithley2400:
    def __init__(self, port="MOCK"):
        self.enabled = False
        self.closed = False
        self.tick = 0

    def configure(self, settings):
        self.settings = settings
        self.enabled = True

    def read(self, channel=None):
        self.tick += 1
        resistance = 1000 + (self.tick % 100) * 0.1
        voltage = (
            self.settings.bias_voltage
            if self.settings.mode == "constant_voltage"
            else 0.1
        )
        current = voltage / resistance
        return Reading(resistance, voltage, current, "simulated")

    def output_off(self):
        self.enabled = False

    def close(self):
        self.closed = True


class MockKeithley2700(MockKeithley2400):
    def set_resistance_range(self, settings):
        self.settings = settings

    def read(self, channel):
        self.tick += 1
        if self.settings.mode == "voltage":
            return Reading(
                voltage=0.1 + channel / 10000,
                status="simulated;current_unavailable_7706;resistance_not_measured",
            )
        return Reading(
            resistance=1000 + channel + self.tick * 0.1,
            status="simulated;current_unavailable_7706;voltage_not_measured",
            resistance_range=next(
                r
                for r in (100, 1000, 10000, 100000, 1000000, 10000000, 100000000)
                if r
                >= (
                    1000 + channel + self.tick * 0.1
                    if self.settings.auto_range
                    else self.settings.manual_range
                )
            ),
        )


class MockGateSupply:
    def __init__(self):
        self.voltage = 0.0
        self.enabled = False
        self.closed = False

    def configure(self, current_limit):
        self.current_limit = current_limit

    def set_voltage(self, voltage):
        self.voltage = voltage

    def output_on(self):
        self.enabled = True

    def output_off(self):
        self.enabled = False

    def read_voltage(self):
        return self.voltage if self.enabled else 0.0

    def close(self):
        self.closed = True


class MockShutterController:
    def __init__(self, port, baud_rate, open_angle=90, closed_angle=0):
        self.is_open = False

    def set_speed(self, speed):
        pass

    def set_open(self, should_open):
        self.is_open = should_open

    def close(self):
        pass


class MockAeraMFCManager:
    def __init__(self, port, ranges, accuracies=None):
        self.ranges = ranges
        self.current_flows = dict.fromkeys(ranges, 0.0)
        self.closed = False

    def set_flow(self, ch, flow):
        if ch not in self.ranges:
            raise ValueError(f"Unknown MFC channel {ch}")
        self.current_flows[ch] = finite(flow, f"MFC {ch}", 0, self.ranges[ch])

    def get_actual_flow(self, ch):
        return self.current_flows[ch]

    def stop_all(self):
        for ch in self.ranges:
            self.set_flow(ch, 0)

    def close(self):
        # Closing the communication must preserve configured failure/purge flows.
        self.closed = True
