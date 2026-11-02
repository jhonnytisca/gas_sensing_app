"""Verify driver parsing, channel routing and unit conversion without instruments."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pyvisa

from gas_sensing_app.config.models import MeasurementSettings
from gas_sensing_app.hardware.aera_mfc import AeraMFCManager
from gas_sensing_app.hardware.keithley_2400 import Keithley2400
from gas_sensing_app.hardware.keithley_2700 import Keithley2700


class Instrument:
    def __init__(self, reading):
        self.reading = reading
        self.commands = []

    def write(self, command):
        self.commands.append(command)

    def query(self, command):
        return '0,"No error"' if command == ":SYST:ERR?" else self.reading


@pytest.mark.parametrize("wires,function", [(2, "RES"), (4, "FRES")])
def test_2700_live_range_commands_and_readback(wires, function):
    from dataclasses import replace

    driver = Keithley2700.__new__(Keithley2700)
    driver.instrument = Mock()
    driver.instrument.query.side_effect = lambda command: {
        ":SYST:ERR?": '0,"No error"',
        ":READ?": "1234.5",
        f":SENS:{function}:RANG?": "10000",
    }[command]
    settings = MeasurementSettings(instrument="2700", wire_mode=wires, last_channel=2)
    driver.configure(settings)
    driver.set_resistance_range(replace(settings, auto_range=False, manual_range=10000))
    driver.instrument.write.assert_any_call(f":SENS:{function}:RANG 10000,(@101,102)")
    driver.instrument.write.assert_any_call(f":SENS:{function}:RANG 10000")
    assert driver.read(101).resistance_range == 10000
    driver.set_resistance_range(settings)
    driver.instrument.write.assert_any_call(f":SENS:{function}:RANG:AUTO ON")


@pytest.mark.parametrize("serial", [True, False])
@pytest.mark.parametrize("driver_class", [Keithley2400, Keithley2700])
def test_meter_serial_termination(monkeypatch, serial, driver_class):
    instrument = Mock(
        interface_type=(
            pyvisa.constants.InterfaceType.asrl
            if serial
            else pyvisa.constants.InterfaceType.gpib
        ),
        read_termination=None,
        write_termination="\r\n",
    )
    manager = Mock()
    manager.open_resource.return_value = instrument
    instrument.query.return_value = (
        f"KEITHLEY INSTRUMENTS INC.,MODEL {driver_class.__name__[-4:]},123,1.0"
    )
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: manager)
    driver = driver_class("ASRL1::INSTR" if serial else "GPIB0::24::INSTR")
    assert instrument.read_termination == ("\r" if serial else None)
    assert instrument.write_termination == ("\r" if serial else "\r\n")
    if serial and driver_class is Keithley2700:
        assert instrument.baud_rate == 9600
        assert instrument.flow_control == pyvisa.constants.ControlFlow.none
    driver.close()
    driver.close()
    instrument.close.assert_called_once()
    manager.close.assert_not_called()


@pytest.mark.parametrize("driver_class", [Keithley2400, Keithley2700])
@pytest.mark.parametrize("failure", ["wrong_model", "timeout"])
def test_connection_failure_closes_only_its_resource(
    monkeypatch, driver_class, failure
):
    instrument = Mock(interface_type=pyvisa.constants.InterfaceType.asrl)
    if failure == "timeout":
        instrument.query.side_effect = pyvisa.errors.VisaIOError(
            pyvisa.constants.StatusCode.error_timeout
        )
    else:
        instrument.query.return_value = "KEITHLEY,MODEL 9999,123,1.0"
    manager = Mock()
    manager.open_resource.return_value = instrument
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: manager)
    with pytest.raises((RuntimeError, pyvisa.errors.VisaIOError)):
        driver_class("ASRL1::INSTR")
    instrument.write.assert_not_called()
    instrument.close.assert_called_once()
    manager.close.assert_not_called()


def test_2400_simultaneous_reading_and_overrange():
    driver = Keithley2400.__new__(Keithley2400)
    driver.instrument = Instrument("1.2,0.003,400")
    driver.configure(MeasurementSettings(wire_mode=4))
    reading = driver.read()
    assert (reading.resistance, reading.voltage, reading.current) == (400, 1.2, 0.003)
    assert ":SYST:RSEN ON" in driver.instrument.commands
    assert ":SENS:FUNC:ON:ALL" in driver.instrument.commands
    driver.instrument.reading = "9.91e37,9.91e37,9.91e37"
    assert driver.read().current is None
    driver.instrument.reading = "bad"
    with pytest.raises(ValueError):
        driver.read()


def test_2700_routes_only_force_channel_for_automatic_kelvin_pair():
    driver = Keithley2700.__new__(Keithley2700)
    driver.instrument = Instrument("1234.5")
    driver.configure(
        MeasurementSettings(instrument="2700", wire_mode=4, last_channel=2)
    )
    reading = driver.read(102)
    assert ':SENS:FUNC "FRES",(@101,102)' in driver.instrument.commands
    assert driver.instrument.commands[-1] == ":ROUT:CLOS (@102)"
    assert reading.resistance == 1234.5
    assert reading.current is None and reading.voltage is None


@pytest.mark.parametrize("slot", [1, 2])
def test_2700_four_two_wire_sensors(slot):
    driver = Keithley2700.__new__(Keithley2700)
    driver.instrument = Instrument("1234.5")
    settings = MeasurementSettings(instrument="2700", slot=slot, last_channel=4)
    driver.configure(settings)
    channels = ",".join(str(slot * 100 + ch) for ch in range(1, 5))
    assert f':SENS:FUNC "RES",(@{channels})' in driver.instrument.commands
    assert ':SENS:FUNC "RES"' in driver.instrument.commands
    for channel in settings.channels:
        assert driver.read(channel).resistance == 1234.5
        assert driver.instrument.commands[-1] == f":ROUT:CLOS (@{channel})"
    driver.output_off()
    assert driver.instrument.commands[-1] == ":ROUT:OPEN:ALL"


@pytest.mark.parametrize("auto_range", [True, False])
def test_2400_fixed_voltage_and_range(auto_range):
    driver = Keithley2400.__new__(Keithley2400)
    driver.instrument = Instrument("0.5,0.000001,500000")
    driver.configure(
        MeasurementSettings(
            mode="constant_voltage",
            bias_voltage=0.5,
            compliance=0.0001,
            auto_range=auto_range,
            manual_range=2000000,
        )
    )
    commands = driver.instrument.commands
    assert ":SOUR:FUNC VOLT" in commands
    assert ":SOUR:VOLT:LEV 0.5" in commands
    assert ":SENS:CURR:PROT 0.0001" in commands
    assert ":SENS:RES:MODE MAN" in commands
    # Enabling RES under auto ohms changes the instrument back to current source.
    assert (
        commands.index(":SENS:RES:MODE MAN")
        < commands.index(':SENS:FUNC "VOLT","CURR","RES"')
        < commands.index(":SOUR:FUNC VOLT")
    )
    assert ":SENS:RES:MODE AUTO" not in commands
    assert not any(command.startswith(":SENS:RES:RANG") for command in commands)
    assert commands[-1] == ":OUTP ON"
    assert driver.read().resistance == 500000


@pytest.mark.parametrize("full_scale", [200, 1000])
def test_mfc_readback_is_already_sccm(full_scale):
    driver = AeraMFCManager.__new__(AeraMFCManager)
    driver.ranges = {1: full_scale}
    driver.rod4 = SimpleNamespace(ch_1=SimpleNamespace(actual_flow=25))
    assert driver.get_actual_flow(1) == 25


@pytest.mark.parametrize(
    "mode,sense", [("constant_current", "VOLT"), ("constant_voltage", "CURR")]
)
def test_2400_pulse_ranges_and_off_on_failure(mode, sense):
    driver = Keithley2400.__new__(Keithley2400)
    driver.instrument = Mock()
    driver.instrument.query.return_value = '0,"No error"'
    driver.configure(
        MeasurementSettings(
            mode=mode,
            pulsed=True,
            source_auto_range=False,
            source_voltage_range=2,
            source_current_range=1e-6,
            voltage_auto_range=False,
            voltage_range=2,
            current_auto_range=False,
            current_range=1e-6,
            settling_s=0.025,
            nplc=2,
        )
    )
    commands = [call.args[0] for call in driver.instrument.write.call_args_list]
    assert ":OUTP ON" not in commands
    assert ":SOUR:CLE:AUTO ON" in commands
    assert ":OUTP:SMOD HIMP" in commands
    assert ":SOUR:DEL 0.025" in commands
    assert ":SENS:VOLT:NPLC 2" in commands
    assert f":SENS:{sense}:RANG:AUTO OFF" in commands
    assert commands.index(
        f":SENS:{sense}:PROT " + ("2.0" if sense == "VOLT" else "0.01")
    ) < commands.index(f":SENS:{sense}:RANG:AUTO OFF")
    if mode == "constant_current":
        assert ":SOUR:CURR:LEV 5e-07" in commands
        assert ":SOUR:CURR:RANG 1e-06" in commands
        assert ":SENS:CURR:RANG:AUTO OFF" not in commands
    driver.instrument.query.return_value = "0.1,5e-7,200000"
    assert driver.read().current == 5e-7
    driver.instrument.write.assert_called_with(":OUTP OFF")
    driver.instrument.query.side_effect = TimeoutError("read timed out")
    with pytest.raises(TimeoutError):
        driver.read()
    driver.instrument.write.assert_called_with(":OUTP OFF")


@pytest.mark.parametrize(
    "mode,wires,function",
    [("resistance", 2, "RES"), ("resistance", 4, "FRES"), ("voltage", 2, "VOLT:DC")],
)
def test_2700_integration_applies_to_channels_and_active_function(
    mode, wires, function
):
    driver = Keithley2700.__new__(Keithley2700)
    driver.instrument = Instrument("1")
    driver.configure(
        MeasurementSettings(
            instrument="2700",
            mode=mode,
            wire_mode=wires,
            nplc=5,
            voltage_auto_range=False,
            voltage_range=10,
        )
    )
    assert f":SENS:{function}:NPLC 5,(@101)" in driver.instrument.commands
    assert f":SENS:{function}:NPLC 5" in driver.instrument.commands
    if mode == "voltage":
        assert ":SENS:VOLT:DC:RANG 10,(@101)" in driver.instrument.commands


def test_real_configuration_snapshots_preserve_raw_readbacks():
    smu = Keithley2400.__new__(Keithley2400)
    smu.identity = "KEITHLEY,MODEL 2400,serial,firmware"
    smu.settings = MeasurementSettings(mode="constant_current", pulsed=True)
    smu.instrument = Mock()
    smu.instrument.query.side_effect = lambda cmd: (
        '0,"No error"' if cmd == ":SYST:ERR?" else "5.000000E-07\n"
    )
    snapshot = smu.configuration_snapshot()
    assert snapshot["identity"] == smu.identity
    assert not snapshot["simulated"]
    assert snapshot["scpi_readbacks"][":SOUR:CURR:LEV?"] == "5.000000E-07"
    assert ":SENS:RES:RANG?" not in snapshot["scpi_readbacks"]
    dmm = Keithley2700.__new__(Keithley2700)
    dmm.identity = "KEITHLEY,MODEL 2700,serial,firmware"
    dmm.settings = MeasurementSettings(instrument="2700", wire_mode=4, last_channel=2)
    dmm.instrument = smu.instrument
    snapshot = dmm.configuration_snapshot()
    assert ":SENS:FRES:NPLC? (@101)" in snapshot["scpi_readbacks"]
    assert ":SENS:FRES:RANG? (@102)" in snapshot["scpi_readbacks"]
