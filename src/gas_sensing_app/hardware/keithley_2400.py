"""Keithley 2400: one acquisition returns V, I and R from the instrument."""

from gas_sensing_app.core.measurement import Reading, measured


class Keithley2400:
    def __init__(self, resource_address):
        import pyvisa

        self.rm = pyvisa.ResourceManager()
        self.instrument = None
        try:
            self.instrument = self.rm.open_resource(resource_address)
            self.instrument.timeout = 5000
            if self.instrument.interface_type == pyvisa.constants.InterfaceType.asrl:
                self.instrument.read_termination = "\r"
                self.instrument.write_termination = "\r"
            self.instrument.write(":OUTP OFF")
            self.instrument.write("*RST")
            self.instrument.write("*CLS")
        except BaseException:
            self.close()
            raise

    def configure(self, settings):
        inst = self.instrument
        inst.write(":OUTP OFF")
        inst.write(":SYST:RSEN " + ("ON" if settings.wire_mode == 4 else "OFF"))
        if settings.mode == "resistance":
            inst.write(":SENS:FUNC 'RES'")
            inst.write(":SENS:RES:MODE AUTO")
        else:
            # Auto ohms switches the source to current when RES is enabled.
            inst.write(":SENS:RES:MODE MAN")
            inst.write(':SENS:FUNC "VOLT","CURR","RES"')
            inst.write(":SOUR:FUNC VOLT")
            inst.write(":SOUR:VOLT:MODE FIX")
            inst.write(f":SOUR:VOLT:LEV {settings.bias_voltage}")
            inst.write(f":SENS:CURR:PROT {settings.compliance}")
        inst.write(":SENS:FUNC:CONC ON")
        inst.write(":SENS:FUNC:ON:ALL")
        inst.write(":SENS:RES:OCOM OFF")
        inst.write(":SENS:RES:RANG:AUTO " + ("ON" if settings.auto_range else "OFF"))
        if not settings.auto_range:
            inst.write(f":SENS:RES:RANG {settings.manual_range}")
        inst.write(":FORM:ELEM VOLT,CURR,RES")
        self.check_error()
        inst.write(":OUTP ON")

    def check_error(self):
        response = self.instrument.query(":SYST:ERR?")
        if int(response.split(",", 1)[0]) != 0:
            raise RuntimeError(f"Keithley 2400: {response}")

    def read(self, channel=None):
        values = self.instrument.query(":READ?").strip().split(",")
        if len(values) != 3:
            raise ValueError(f"Expected V,I,R from 2400, received {values!r}")
        voltage, current, resistance = map(measured, values)
        return Reading(
            resistance,
            voltage,
            current,
            "ok"
            if None not in (voltage, current, resistance)
            else "overrange_or_unavailable",
        )

    def output_off(self):
        if self.instrument is not None:
            self.instrument.write(":OUTP OFF")

    def close(self):
        try:
            if self.instrument is not None:
                self.instrument.close()
        finally:
            self.rm.close()
