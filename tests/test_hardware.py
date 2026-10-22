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
    assert (":SENS:RES:RANG 2000000" in commands) is not auto_range
    assert commands[-1] == ":OUTP ON"
    assert driver.read().resistance == 500000


def test_mfc_percent_to_sccm():
    driver = AeraMFCManager.__new__(AeraMFCManager)
    driver.ranges = {1: 200}
    driver.rod4 = SimpleNamespace(ch_1=SimpleNamespace(actual_flow=25))
    assert driver.get_actual_flow(1) == 50
