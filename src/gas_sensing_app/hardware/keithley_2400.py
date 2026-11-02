"""Keithley 2400: one acquisition returns V, I and R from the instrument."""

from gas_sensing_app.core.measurement import Reading, measured


class Keithley2400:
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
            identity = self.instrument.query("*IDN?").strip()
            self.identity = identity
            fields = identity.upper().split(",")
            if len(fields) < 2 or fields[1].strip() != "MODEL 2400":
                raise RuntimeError(
                    f"Expected Keithley 2400 at {resource_address}, "
                    f"received {identity!r}"
                )
            self.instrument.write(":OUTP OFF")
            self.instrument.write("*RST")
            self.instrument.write("*CLS")
        except BaseException:
            self.close()
            raise

    def configure(self, settings):
        settings.validate()
        self.settings = settings
        inst = self.instrument
        inst.write(":OUTP OFF")
        # High impedance disconnects the sample between measurements.
        inst.write(":OUTP:SMOD HIMP")
        inst.write(":SOUR:CLE:AUTO " + ("ON" if settings.pulsed else "OFF"))
        inst.write(":SOUR:DEL:AUTO OFF")
        inst.write(f":SOUR:DEL {settings.settling_s:g}")
        inst.write(":TRIG:COUN 1")
        inst.write(":TRIG:DEL 0")
        inst.write(":SYST:RSEN " + ("ON" if settings.wire_mode == 4 else "OFF"))
        if settings.mode == "resistance":
            inst.write(":SENS:FUNC 'RES'")
            inst.write(":SENS:RES:MODE AUTO")
        else:
            # Enabling RES in auto ohms would override the chosen source.
            inst.write(":SENS:RES:MODE MAN")
            inst.write(':SENS:FUNC "VOLT","CURR","RES"')
        inst.write(":SENS:FUNC:CONC ON")
        inst.write(":SENS:FUNC:ON:ALL")
        inst.write(":SENS:RES:OCOM OFF")
        if settings.mode == "resistance":
            inst.write(
                ":SENS:RES:RANG:AUTO " + ("ON" if settings.auto_range else "OFF")
            )
            if not settings.auto_range:
                inst.write(f":SENS:RES:RANG {settings.manual_range}")
        else:
            self.configure_source(settings)
        # Integration speed is global on the 2400.
        inst.write(f":SENS:VOLT:NPLC {settings.nplc:g}")
        inst.write(":FORM:ELEM VOLT,CURR,RES")
        inst.timeout = max(5000, int((settings.settling_s + 5) * 1000))
        self.check_error()
        if not settings.pulsed:
            inst.write(":OUTP ON")

    def configure_source(self, settings):
        inst = self.instrument
        current = settings.mode == "constant_current"
        function = "CURR" if current else "VOLT"
        sense = "VOLT" if current else "CURR"
        level = settings.source_current if current else settings.bias_voltage
        source_range = (
            settings.source_current_range if current else settings.source_voltage_range
        )
        inst.write(f":SOUR:FUNC {function}")
        inst.write(f":SOUR:{function}:MODE FIX")
        inst.write(
            f":SOUR:{function}:RANG:AUTO "
            + ("ON" if settings.source_auto_range else "OFF")
        )
        if not settings.source_auto_range:
            inst.write(f":SOUR:{function}:RANG {source_range:g}")
        inst.write(f":SOUR:{function}:LEV {level}")
        compliance = settings.voltage_compliance if current else settings.compliance
        inst.write(f":SENS:{sense}:PROT {compliance}")
        auto = settings.voltage_auto_range if current else settings.current_auto_range
        value = settings.voltage_range if current else settings.current_range
        inst.write(f":SENS:{sense}:RANG:AUTO " + ("ON" if auto else "OFF"))
        if not auto:
            inst.write(f":SENS:{sense}:RANG {value:g}")

    def configuration_snapshot(self):
        commands = [
            ":SYST:LFR?",
            ":SYST:RSEN?",
            ":SOUR:FUNC?",
            ":SENS:RES:MODE?",
            ":SENS:VOLT:NPLC?",
            ":SOUR:DEL?",
            ":SOUR:CLE:AUTO?",
            ":OUTP:SMOD?",
        ]
        if self.settings.mode == "resistance":
            commands += [":SENS:RES:RANG:AUTO?", ":SENS:RES:RANG?"]
        else:
            source = "CURR" if self.settings.mode == "constant_current" else "VOLT"
            sense = "VOLT" if source == "CURR" else "CURR"
            commands += [
                f":SOUR:{source}:LEV?",
                f":SOUR:{source}:RANG?",
                f":SOUR:{source}:RANG:AUTO?",
                f":SENS:{sense}:PROT?",
                f":SENS:{sense}:RANG?",
                f":SENS:{sense}:RANG:AUTO?",
            ]
        snapshot = {
            "simulated": False,
            "identity": self.identity,
            "scpi_readbacks": {
                cmd: self.instrument.query(cmd).strip() for cmd in commands
            },
        }
        self.check_error()
        return snapshot

    def check_error(self):
        response = self.instrument.query(":SYST:ERR?")
        if int(response.split(",", 1)[0]) != 0:
            raise RuntimeError(f"Keithley 2400: {response}")

    def read(self, channel=None):
        try:
            # Source auto-clear turns on for the source-delay-measure cycle and
            # switches off inside the instrument, before READ? returns.
            values = self.instrument.query(":READ?").strip().split(",")
        finally:
            if self.settings.pulsed:
                self.output_off()
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
        # The VISA manager is shared with other drivers, including the MFC.
        if self.instrument is not None:
            self.instrument.close()
            self.instrument = None
