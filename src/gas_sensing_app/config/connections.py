"""Computer-local transport assignments; never exported in experiment profiles."""

from pathlib import Path

import yaml

TRANSPORT_FIELDS = {
    "keithley_2400": ("port", "baud_rate", "read_termination"),
    "keithley_2700": ("port", "baud_rate", "read_termination"),
    "mfc_controller": ("port",),
    "shutter": ("port", "baud_rate"),
}


def local_connections_path():
    from PyQt6.QtCore import QStandardPaths

    return (
        Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppConfigLocation
            )
        )
        / "device_connections.yaml"
    )


def connection_values(config):
    return {
        device: {key: getattr(getattr(config.hardware, device), key) for key in fields}
        for device, fields in TRANSPORT_FIELDS.items()
    }


def apply_connections(config, values):
    if not isinstance(values, dict):
        raise ValueError("Device connections must be a mapping")
    updates = []
    for device, fields in TRANSPORT_FIELDS.items():
        raw = values.get(device, {})
        if not isinstance(raw, dict):
            raise ValueError(f"Connections for {device} must be a mapping")
        for key in fields:
            if key not in raw:
                continue
            value = raw[key]
            validate_transport_value(device, key, value)
            updates.append((getattr(config.hardware, device), key, value))
    for target, key, value in updates:
        setattr(target, key, value)


def validate_transport_value(device, key, value):
    if key == "baud_rate":
        if type(value) is not int or not 1 <= value <= 4000000:
            raise ValueError(f"Invalid baud rate for {device}")
    elif not isinstance(value, str):
        raise ValueError(f"{device}.{key} must be text")
    elif key == "read_termination" and value not in ("\r", "\n", "\r\n"):
        raise ValueError("Read termination must be CR, LF or CR+LF")


def load_local_connections(config, path=None):
    path = Path(path) if path is not None else local_connections_path()
    if path.exists():
        apply_connections(config, yaml.safe_load(path.read_text(encoding="utf-8")))


def save_local_connections(config, path=None):
    from .profiles import atomic_yaml

    atomic_yaml(path or local_connections_path(), connection_values(config))


def required_devices(config, measurement):
    devices = [f"keithley_{measurement.instrument}", "mfc_controller"]
    if config.hardware.shutter.enabled:
        devices.append("shutter")
    return devices


def connection_problems(config, measurement):
    if config.hardware.use_mock:
        return []
    from gas_sensing_app.find_ports import visa_address

    problems, used = [], set()
    for device in required_devices(config, measurement):
        address = getattr(config.hardware, device).port.strip()
        if not address or address.upper() in ("MOCK", "NONE", "NOT CONFIGURED"):
            problems.append(f"Choose a port for {device.replace('_', ' ')}")
            continue
        canonical = (
            visa_address(address)
            if address.upper().startswith("COM") or address.startswith("/")
            else address
        )
        if canonical in used:
            problems.append(
                f"Port {address} is assigned to more than one required device"
            )
        used.add(canonical)
    return problems
