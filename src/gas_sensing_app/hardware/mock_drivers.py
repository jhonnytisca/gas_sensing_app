import random


class MockKeithley2400:
    def __init__(self, port):
        print(f"[MOCK] Keithley 2400 initialized on virtual port {port}")
        self.four_wire = False
        # Reference a shared state tracker if you want interactive physics simulation

    def setup_resistance(self, **kwargs):
        print(f"[MOCK] Keithley configured with settings: {kwargs}")
        self.four_wire = kwargs.get("four_wire", False)

    def get_reading(self) -> float:
        """Simulates fluctuating baseline resistance."""
        baseline = 100.0 if not self.four_wire else 102.5
        return baseline + random.uniform(-0.05, 0.05)

    def close(self):
        print("[MOCK] Keithley connection closed.")


class MockShutterController:
    def __init__(self, port, baud_rate, open_angle=90, closed_angle=0):
        self.open_angle = open_angle
        self.closed_angle = closed_angle
        self.is_open = False
        print(f"[MOCK] Shutter ready on {port} (Baud: {baud_rate})")

    def set_speed(self, speed):
        pass

    def set_open(self, should_open: bool):
        self.is_open = should_open
        state = "OPEN" if should_open else "CLOSED"
        angle = self.open_angle if should_open else self.closed_angle
        print(f"[MOCK] Shutter hardware moved to {state} ({angle}°)")

    def close(self):
        print("[MOCK] Shutter connection closed.")


class MockAeraMFCManager:
    def __init__(self, port, ranges, accuracies=None):
        print(f"[MOCK] MFC Manager active on {port} with channel ceilings {ranges}")
        self.ranges = ranges or {1: 1000, 2: 1000, 3: 200, 4: 200}
        self.accuracies = accuracies or {}
        self.current_flows = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}

    def set_flow(self, ch: int, flow: float):
        if ch not in self.ranges:
            print(f"[MOCK Error]: Channel {ch} not configured.")
            return

        if flow < 0:
            print(
                f"[MOCK INFO]: Negative flow setpoint ({flow} sccm) ignored on Ch {ch}."
            )
            return

        max_val = self.ranges[ch]
        if flow > max_val:
            print(
                f"[MOCK Error]: Specified flow {flow} sccm exceeds maximum capacity "
                f"({max_val} sccm) for Ch {ch}. Command Rejected."
            )
            return

        acc_fraction = 0.0
        if isinstance(self.accuracies, dict):
            acc_fraction = self.accuracies.get(ch, 0.0)
        elif isinstance(self.accuracies, (int, float)):
            acc_fraction = float(self.accuracies)

        accuracy_threshold = acc_fraction * max_val
        if 0 < flow < accuracy_threshold:
            print(
                f"[MOCK Warning]: Setpoint {flow} sccm is below the recommended "
                f"physical accuracy limit ({accuracy_threshold} sccm) for Ch {ch}."
            )

        self.current_flows[ch] = float(flow)
        print(f"[MOCK] MFC Ch {ch} physical valve adjusted to {flow} sccm")

    def get_actual_flow(self, ch: int) -> float:
        target = self.current_flows.get(ch, 0.0)
        if target == 0.0:
            return 0.0
        return target + random.uniform(-0.2, 0.2)

    def stop_all(self):
        print("[MOCK] Emergency Broadcast: All MFC gas lines zeroed out.")
        self.current_flows = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}

    def close(self):
        print("[MOCK] MFC controller connection closed.")
