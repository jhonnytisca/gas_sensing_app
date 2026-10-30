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
            identity = self.instrument.query("*IDN?").strip()
            fields = identity.upper().split(",")
            if len(fields) < 2 or fields[1].strip() != "MODEL 2700":
                raise RuntimeError(
                    f"Expected Keithley 2700 at {resource_address}, "
                    f"received {identity!r}"
                )
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
        # READ? after individual relay closure uses the active DMM function.
        self.instrument.write(f':SENS:FUNC "{function}"')
        self.instrument.write(":FORM:ELEM READ")
        self.instrument.write(":TRIG:COUN 1")
        self.instrument.write(":SAMP:COUN 1")
        if settings.mode == "resistance":
            self.set_resistance_range(settings)
        self.check_error()

    def check_error(self):
        response = self.instrument.query(":SYST:ERR?")
        if int(response.split(",", 1)[0]) != 0:
            raise RuntimeError(f"Keithley 2700: {response}")

    def set_resistance_range(self, settings):
        settings.validate()
        function = "FRES" if settings.wire_mode == 4 else "RES"
        command = (
            f":SENS:{function}:RANG:AUTO ON"
            if settings.auto_range
            else f":SENS:{function}:RANG {settings.manual_range:g}"
        )
        channels = ",".join(map(str, settings.channels))
        self.instrument.write(f"{command},(@{channels})")
        self.instrument.write(command)
        self.check_error()
        self.settings = settings

    def read(self, channel):
        # ROUT:CLOS automatically pairs n and n+10 for FRES on the 7706.
        self.instrument.write(f":ROUT:CLOS (@{channel})")
        value = measured(self.instrument.query(":READ?").strip())
        status = "overrange" if value is None else "ok"
        if self.settings.mode == "voltage":
            return Reading(voltage=value, status=status)
        function = "FRES" if self.settings.wire_mode == 4 else "RES"
        actual_range = float(self.instrument.query(f":SENS:{function}:RANG?"))
        return Reading(
            resistance=value,
            status=status,
            resistance_range=actual_range,
        )

    def output_off(self):
        if self.instrument is not None:
            try:
                self.instrument.write(":ABOR")
            finally:
                self.instrument.write(":ROUT:OPEN:ALL")

    def close(self):
        # The VISA manager is shared with other drivers, including the MFC.
        if self.instrument is not None:
            self.instrument.close()
            self.instrument = None
