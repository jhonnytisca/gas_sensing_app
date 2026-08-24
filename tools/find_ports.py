import platform
import sys


def main():
    print("=" * 60)
    print("          LAB HARDWARE PORT DISCOVERY UTILITY          ")
    print("=" * 60)
    print(f"Operating System: {platform.system()} ({platform.release()})")
    print(f"Python Runtime:   {sys.executable}\n")

    # 1. Query System Serial Ports via PySerial (Great for USB Descriptions)
    try:
        import serial.tools.list_ports

        ports = sorted(serial.tools.list_ports.comports())

        print("--- 1. Connected USB/Serial Devices (PySerial) ---")
        if not ports:
            print("  [!] No physical serial devices detected on USB buses.")
        for p in ports:
            print(f"  📍 Port String: {p.device}")
            print(f"     Description: {p.description}")
            print(f"     Hardware ID: {p.hwid}")
            print("  " + "-" * 45)
    except ImportError:
        print("  [X] PySerial is not installed or active in this environment.")

    print("\n")

    # 2. Query PyVISA Resource Manager (Great for exact config.yaml string syntax)
    try:
        import pyvisa

        print("--- 2. Active VISA Resource Strings (PyVISA @py) ---")
        try:
            # Explicitly checking through the pure-python backend layer
            rm = pyvisa.ResourceManager("@py")
            resources = rm.list_resources()

            if not resources:
                print("  [!] No active instrumentation addresses mapped by PyVISA-py.")
            for res in resources:
                print(f'  🔌 YAML Target: "{res}"')
        except Exception as e:
            print(f"  [X] Error polling VISA backend: {e}")
    except ImportError:
        print("  [X] PyVISA is not installed or active in this environment.")

    print("=" * 60)
    print("Copy the designated Port String or YAML Target into your config.yaml")
    print("=" * 60)


if __name__ == "__main__":
    main()
