from gas_sensing_app.config.config import Config


def test_load_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
hardware:
  use_mock: true
  keithley_2400:
    port: MOCK
    auto_range: false
    manual_range: 200000
    four_wire: true
  shutter:
    port: MOCK
    baud_rate: 115200
    open_angle: 90
    closed_angle: 0
  mfc_controller:
    port: MOCK
    range_sccm:
      1: 1000
      2: 1000
      3: 200
      4: 200
logging:
  data_log:
    folder: data
    filename_prefix: test
  console_log:
    enabled: false
    folder: logs
    filename_prefix: test
"""
    )

    config = Config(config_file).load()

    assert config.hardware.use_mock is True
    assert config.hardware.keithley_2400.port == "MOCK"


def test_measurement_integration_and_source_validation():
    from dataclasses import replace

    import pytest

    from gas_sensing_app.config.models import MeasurementSettings

    settings = MeasurementSettings(mode="constant_current")
    settings.validate()
    for changes in (
        {"nplc": 11},
        {"nplc": float("nan")},
        {"settling_s": -1},
        {"source_current": 2},
        {"voltage_compliance": 0},
        {"pulsed": "yes"},
        {"source_auto_range": False, "source_current": 1e-3},
    ):
        with pytest.raises(ValueError):
            replace(settings, **changes).validate()
    replace(settings, instrument="2700", mode="resistance", nplc=50).validate()
