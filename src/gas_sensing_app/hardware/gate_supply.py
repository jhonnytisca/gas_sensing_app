"""Gate supply boundary. Transport is intentionally independent of sequencing."""

from typing import Protocol


class GateSupply(Protocol):
    def configure(self, current_limit: float) -> None: ...
    def set_voltage(self, voltage: float) -> None: ...
    def output_on(self) -> None: ...
    def output_off(self) -> None: ...
    def read_voltage(self) -> float | None: ...
    def close(self) -> None: ...


class EAPS3065:
    """Adapter for a future verified EA transport implementing GateSupply.

    No SCPI/serial protocol is assumed for the EA-PS 3065-03 B.
    The laboratory must supply a verified transport before real gate operation.
    """

    def __init__(self, transport):
        self.transport = transport

    def configure(self, current_limit):
        self.transport.configure(current_limit)

    def set_voltage(self, voltage):
        self.transport.set_voltage(voltage)

    def output_on(self):
        self.transport.output_on()

    def output_off(self):
        self.transport.output_off()

    def read_voltage(self):
        return self.transport.read_voltage()

    def close(self):
        self.transport.close()
