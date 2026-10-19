"""2700 / 7706 passive measurements. Four-wire pairs are channel n and n+10.

The 7706 has no DCI input path. Do not fabricate current from an ohms reading.
"""

from gas_sensing_app.core.measurement import Reading, measured


class Keithley2700:
    def __init__(self, resource_address, baud_rate=9600, read_termination="\r"):
        import pyvisa

        self.rm = pyvisa.ResourceManager()
        self.instrument = None
        try:
            self.instrument = self.rm.open_resource(resource_address)
            self.instrument.timeout = 5000
            if self.instrument.interface_type == pyvisa.constants.InterfaceType.asrl:
                self.instrument.baud_rate = baud_rate
                self.instrument.read_termination = read_termination
                self.instrument.write_termination = "\r"
                self.instrument.flow_control = pyvisa.constants.ControlFlow.none
            self.instrument.write("*RST")
            self.instrument.write("*CLS")
            self.instrument.write(":ROUT:OPEN:ALL")
        except BaseException:
            self.close()
            raise

    def configure(self, settings):
        self.settings = settings
        channels = ",".join(str(ch) for ch in settings.channels)
        function = (
            "VOLT:DC"
            if settings.mode == "voltage"
            else ("FRES" if settings.wire_mode == 4 else "RES")
        )
        self.instrument.write(f':SENS:FUNC "{function}",(@{channels})')
        self.instrument.write(":FORM:ELEM READ")
        self.instrument.write(":TRIG:COUN 1")
        self.instrument.write(":SAMP:COUN 1")
        response = self.instrument.query(":SYST:ERR?")
        if int(response.split(",", 1)[0]) != 0:
            raise RuntimeError(f"Keithley 2700: {response}")

    def read(self, channel):
        # ROUT:CLOS automatically pairs n and n+10 for FRES on the 7706.
        self.instrument.write(f":ROUT:CLOS (@{channel})")
        value = measured(self.instrument.query(":READ?").strip())
        status = "current_unavailable_7706"
        if value is None:
            status += ";overrange"
        if self.settings.mode == "voltage":
            return Reading(voltage=value, status=status + ";resistance_not_measured")
        return Reading(resistance=value, status=status + ";voltage_not_measured")

    def output_off(self):
        if self.instrument is not None:
            try:
                self.instrument.write(":ABOR")
            finally:
                self.instrument.write(":ROUT:OPEN:ALL")

    def close(self):
        try:
            if self.instrument is not None:
                self.instrument.close()
        finally:
            self.rm.close()
