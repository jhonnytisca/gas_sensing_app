import time

from pymeasure.instruments.proterial import ROD4


class AeraMFCManager:
    def __init__(
        self, port="ASRL/dev/cu.usbserial-130::INSTR", ranges=None, accuracies=None
    ):
        """
        :param port: The PyVISA resource name
        :param ranges: Dictionary mapping channel index to max sccm
        :param accuracies: Dictionary mapping channel index to a 0-1 accuracy fraction
        """
        try:
            self.rod4 = ROD4(port)
        except Exception as e:
            print(f"Error connecting to ROD-4: {e}")
            raise

        self.ranges = ranges or {1: 1000, 2: 1000, 3: 200, 4: 200}
        self.accuracies = accuracies or {}
        self._initialize_channels()

    def _initialize_channels(self):
        print("Initializing Aera ROD-4 Channels...")
        for ch_idx, max_range in self.ranges.items():
            channel = getattr(self.rod4, f"ch_{ch_idx}")
            channel.mfc_range = max_range
            channel.flow_unit_display = "sccm"
            channel.valve_mode = "flow"
        print("MFCs Ready.")

    def set_flow(self, channel_idx, sccm):
        """Sets the flow rate in sccm with comprehensive validation safeguards."""
        if channel_idx not in self.ranges:
            print(f"Error: Channel {channel_idx} not configured.")
            return

        # 1. Negative numbers are explicitly ignored
        if sccm < 0:
            print(
                f"[INFO]: Negative flow setpoint ({sccm} sccm) "
                f"ignored on Ch {channel_idx}."
            )
            return

        max_val = self.ranges[channel_idx]

        # 2. Maximum range check: show an error in the log and do NOT coerce the value
        if sccm > max_val:
            print(
                f"Error: Specified flow {sccm} sccm exceeds maximum capacity "
                f"({max_val} sccm) for Ch {channel_idx}. Command Rejected."
            )
            return

        # 3. Accuracy warning boundary check
        # (0-1 fraction from configuration matching range layout)
        acc_fraction = 0.0
        if isinstance(self.accuracies, dict):
            acc_fraction = self.accuracies.get(channel_idx, 0.0)
        elif isinstance(self.accuracies, (int, float)):
            acc_fraction = float(self.accuracies)

        accuracy_threshold = acc_fraction * max_val
        if 0 < sccm < accuracy_threshold:
            print(
                f"Warning: Setpoint {sccm} sccm is below the recommended physical "
                f"accuracy limit ({accuracy_threshold} sccm) for Ch {channel_idx}."
            )

        # Send command safely to the hardware
        channel = getattr(self.rod4, f"ch_{channel_idx}")
        channel.setpoint = sccm / max_val * 100  # Normalize to 0-100% scale
        print(f"Channel {channel_idx} set to {sccm} sccm.")

    def get_actual_flow(self, channel_idx):
        channel = getattr(self.rod4, f"ch_{channel_idx}")
        return channel.actual_flow

    def stop_all(self):
        for i in self.ranges.keys():
            channel = getattr(self.rod4, f"ch_{i}")
            channel.setpoint = 0
        print("All MFC flows set to 0.")

    def close(self):
        print("Shutting down AeraMFCManager...")
        self.stop_all()
        time.sleep(0.5)
        self.rod4.shutdown()
        print("Connection closed.")
