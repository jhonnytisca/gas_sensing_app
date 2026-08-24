import time

import serial


class ShutterController:
    def __init__(
        self,
        port="/dev/cu.usbmodem11301",
        baudrate=115200,
        open_angle=90,
        closed_angle=0,
    ):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)  # Critical: Wait for Arduino to reboot after serial opening

        # Save custom calibration bounds from configuration
        self.open_angle = open_angle
        self.closed_angle = closed_angle

        print(
            f"Shutter Controller Connected at {port} with baudrate {baudrate} "
            f"(Open: {open_angle}°, Closed: {closed_angle}°)."
        )

    def _send_command(self, cmd_char, value_str):
        """Internal helper to format and send: <C###>"""
        payload = f"<{cmd_char}{value_str}>"
        self.ser.write(payload.encode("ascii"))

        # Read the acknowledgment: [OK###]
        response = self.ser.readline().decode("ascii").strip()
        return response

    def set_position(self, angle):
        """Sets the shutter angle (0-180). Example: <P090>"""
        angle = max(0, min(180, int(angle)))  # Safety clamp
        # Format to 3 digits with leading zeros
        val_str = f"{angle:03d}"
        return self._send_command("P", val_str)

    def set_speed(self, delay_ms):
        """Sets movement delay (0-250ms). 0 = instant."""
        delay = max(0, min(250, int(delay_ms)))
        val_str = f"{delay:03d}"
        return self._send_command("S", val_str)

    def get_position(self):
        """Queries current position: <GPOS>"""
        return self._send_command("G", "POS")

    def set_open(self, should_open: bool):
        """Bridges API alignment with worker thread state cycles."""
        angle = self.open_angle if should_open else self.closed_angle
        self.set_position(angle)

    def shutter_open(self):
        self.set_position(self.open_angle)

    def shutter_close(self):
        self.set_position(self.closed_angle)

    def close(self):
        self.ser.close()


# --- Manual Test ---
if __name__ == "__main__":
    # Force it to use your active Mac port and configuration angles
    shutter = ShutterController(
        port="/dev/cu.usbmodem1201", baudrate=115200, open_angle=50, closed_angle=60
    )

    print("Starting shutter isolation stress test...")
    shutter.set_speed(0)  # Instant movement

    try:
        for i in range(5):
            print(f"Cycle {i + 1}: Opening Shutter...")
            shutter.set_open(True)
            time.sleep(1.5)

            print(f"Cycle {i + 1}: Closing Shutter...")
            shutter.set_open(False)
            time.sleep(1.5)

        print("Stress test completed successfully without disconnections!")

    except Exception as e:
        print(f"\n[CRASH DETECTED]: The hardware layer threw an error: {e}")

    finally:
        shutter.close()
