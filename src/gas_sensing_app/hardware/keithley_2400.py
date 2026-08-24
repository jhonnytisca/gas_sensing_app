import time

import pyvisa


class Keithley2400:
    def __init__(self, resource_string):
        # self.rm = pyvisa.ResourceManager()
        self.rm = pyvisa.ResourceManager("@py")
        self.inst = self.rm.open_resource(resource_string)
        self.inst.baud_rate = 9600
        self.inst.read_termination = "\r"
        self.inst.write_termination = "\r"
        self.inst.timeout = 5000

        # Initial Reset and Clear
        self.inst.write("*RST")
        self.inst.write("*CLS")
        print(f"Keithley 2400 connected at {resource_string}.")
        time.sleep(0.5)

    def setup_resistance(self, auto_range=True, manual_range=None, four_wire=False):
        """Configure the device for resistance measurement."""
        sense_str = "4-Wire (Remote)" if four_wire else "2-Wire (Local)"
        print(
            f"Configuring Keithley for Resistance ({sense_str}, "
            f"Auto-Range: {auto_range})..."
        )

        # Clear any existing data in the buffer
        self.inst.write(":TRAC:CLEAR")

        commands = [
            ":SENS:FUNC 'RES'",  # Select resistance function
            ":SENS:RES:MODE MAN",  # Manual Ohms mode
        ]

        # Configure 2-wire vs 4-wire remote sensing
        if four_wire:
            commands.append(":SYST:RSEN ON")  # Remote Sense On (4-wire)
        else:
            commands.append(":SYST:RSEN OFF")  # Remote Sense Off (2-wire)

        # Configure Ranging
        if auto_range:
            commands.append(":SENS:RES:RANG:AUTO ON")
        else:
            commands.append(":SENS:RES:RANG:AUTO OFF")
            if manual_range is not None:
                commands.append(f":SENS:RES:RANG {manual_range}")
            else:
                print("Warning: Manual range selected but no range value provided.")

        commands.append(":OUTP ON")  # Turn output on

        for cmd in commands:
            self.inst.write(cmd)
            time.sleep(0.1)  # Give the old processor time to breathe

    def get_reading(self):
        """Call this inside your 1s loop. No setup, just data."""
        try:
            # We use :FETCH? or :READ?
            # :READ? triggers a new acquisition
            raw_data = self.inst.query(":READ?")
            parts = raw_data.split(",")
            return float(parts[2]) if len(parts) >= 3 else None
        except Exception as e:
            return f"Error: {e}"

    def close(self):
        self.inst.write(":OUTP OFF")
        self.inst.close()


# --- The Master Loop (Your 1s Data Acquisition) ---
if __name__ == "__main__":
    PORT = "ASRL/dev/cu.usbserial-120::INSTR"
    sensor = Keithley2400(PORT)

    # SETUP ONCE
    sensor.setup_resistance()

    print("\nStarting 1s logging loop. Press Ctrl+C to stop.\n")
    try:
        while True:
            start_time = time.time()

            value = sensor.get_reading()
            print(f"[{time.strftime('%H:%M:%S')}] Resistance: {value:.4e} Ohms")

            # Precise 1s timing (compensating for command execution time)
            elapsed = time.time() - start_time
            time.sleep(max(0, 1.0 - elapsed))

    except KeyboardInterrupt:
        print("\nStopping experiment...")

    finally:
        sensor.inst.write(":OUTP OFF")
        sensor.inst.close()
