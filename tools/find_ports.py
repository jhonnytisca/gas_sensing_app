# /// script
# requires-python = ">=3.10"
# dependencies = ["pyserial", "pyvisa", "pyvisa-py", "pyyaml"]
# ///
"""List ports without opening devices; optionally print a guided YAML fragment."""

import argparse
import sys

import pyvisa
import yaml
from serial.tools import list_ports


def visa_address(port):
    return f"ASRL{port[3:] if port.upper().startswith('COM') else port}::INSTR"


def discover():
    ports = sorted(list_ports.comports())
    serial_ports = [port.device for port in ports]
    resources = [visa_address(port) for port in serial_ports]
    for port in ports:
        print(f"{port.device}: {port.description} ({port.hwid})")
    try:
        manager = pyvisa.ResourceManager()
        try:
            resources.extend(manager.list_resources())
        finally:
            manager.close()
    except Exception as exc:
        print(f"VISA discovery unavailable: {exc}")
    resources = sorted(set(resources))
    print("\nVISA addresses (discovery does not confirm a responding instrument):")
    for resource in resources:
        print(f"  {resource}")
    if not serial_ports and not resources:
        print("No ports found. Check cables and drivers on the lab computer.")
    return serial_ports, resources


def select(label, addresses):
    print(f"\n{label}")
    for number, address in enumerate(addresses, 1):
        print(f"  {number}. {address}")
    print("  0. Not connected")
    while True:
        answer = input("Choose a number: ").strip()
        if answer.isdigit() and 0 <= int(answer) <= len(addresses):
            return addresses[int(answer) - 1] if int(answer) else None
        print("Enter one of the listed numbers.")


def configure(serial_ports, resources):
    print(
        "\nMatch ports using cable labels. If uncertain, unplug one USB adapter, "
        "rerun discovery, and compare the list. Device names alone are not proof."
    )
    meter = select("Measurement instrument", ["Keithley 2400", "Keithley 2700"])
    if meter is None:
        print("A measurement instrument is required; no YAML generated.")
        return
    model = meter.split()[-1]
    meter_port = select(f"Port for {meter}", resources)
    if meter_port is None:
        print("Connect the selected meter and rerun; no YAML generated.")
        return
    mfc_port = select(
        "Port for the Aera ROD-4 / MFC controller",
        [address for address in resources if address != meter_port],
    )
    shutter_port = select(
        "Port for the shutter controller",
        [
            port
            for port in serial_ports
            if visa_address(port) not in {meter_port, mfc_port}
        ],
    )
    hardware = {
        "use_mock": False,
        f"keithley_{model}": {"port": meter_port},
        "shutter": {"enabled": shutter_port is not None},
    }
    if shutter_port:
        hardware["shutter"].update(port=shutter_port, baud_rate=115200)
    if mfc_port:
        hardware["mfc_controller"] = {"port": mfc_port}
    print("\nMerge these entries into config.yaml; keep your other settings.")
    print("Do not append duplicate hardware/measurement/gate sections.\n")
    print(
        yaml.safe_dump(
            {
                "hardware": hardware,
                "measurement": {"instrument": model},
                "gate": {"enabled": False},
            },
            sort_keys=False,
        )
    )
    if not mfc_port:
        print(
            "NOT READY TO RUN: the app currently requires the MFC controller. "
            "There is no supported MFC enabled:false setting. "
            "Connect it or add meter-only support before acquisition."
        )
    print(
        "The unselected Keithley is not needed. Restart after editing. "
        "Discovery does not verify baud rate, permissions, or communication."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yaml", action="store_true", help="choose devices and print YAML"
    )
    args = parser.parse_args()
    serial_ports, resources = discover()
    if args.yaml:
        configure(serial_ports, resources)
    else:
        print("\nAdd --yaml to choose devices and print configuration entries.")


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\nCancelled; no configuration files changed.")
