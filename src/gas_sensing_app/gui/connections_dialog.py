"""Device addresses local to this computer; discovery never opens devices."""

from copy import deepcopy

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gas_sensing_app.config.connections import (
    apply_connections,
    connection_problems,
    connection_values,
    local_connections_path,
)
from gas_sensing_app.find_ports import scan_resources, visa_address


class DiscoveryWorker(QThread):
    found = pyqtSignal(dict)

    def run(self):
        try:
            self.found.emit(scan_resources())
        except Exception as exc:
            self.found.emit({"serial": [], "visa": [], "error": str(exc)})


class ConnectionsDialog(QDialog):
    def __init__(self, config, measurement, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device connections · this computer")
        self.resize(690, 650)
        self.config = deepcopy(config)
        self.measurement = measurement
        self.worker = None
        self.closing_after_scan = False
        layout = QVBoxLayout(self)
        note = QLabel(
            "Assign the selected Keithley and the MFC controller. The shutter is "
            "required only when enabled. Match adapter labels to your devices; "
            "discovery does not verify instrument identity. You can type an address."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.simulated = QCheckBox("Use simulated devices")
        self.simulated.setChecked(config.hardware.use_mock)
        layout.addWidget(self.simulated)
        self.shutter_enabled = QCheckBox("Enable shutter controller")
        self.shutter_enabled.setChecked(config.hardware.shutter.enabled)
        layout.addWidget(self.shutter_enabled)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        form = QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.ports, self.bauds, self.terminations = {}, {}, {}
        for device, fields in connection_values(config).items():
            title = (
                device.replace("_", " ")
                .replace("mfc controller", "MFC / ROD-4")
                .title()
            )
            port = QComboBox()
            port.setEditable(True)
            port.addItem(fields["port"], fields["port"])
            self.ports[device] = port
            form.addRow(f"{title} port", port)
            if "baud_rate" in fields:
                baud = QSpinBox()
                baud.setRange(1, 4000000)
                baud.setValue(fields["baud_rate"])
                self.bauds[device] = baud
                form.addRow("Serial baud rate", baud)
            if "read_termination" in fields:
                termination = QComboBox()
                for label, value in (("CR", "\r"), ("LF", "\n"), ("CR + LF", "\r\n")):
                    termination.addItem(label, value)
                termination.setCurrentIndex(
                    termination.findData(fields["read_termination"])
                )
                self.terminations[device] = termination
                form.addRow("Serial read termination", termination)
        scroll.setWidget(page)
        layout.addWidget(scroll, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh = QPushButton("Refresh available ports")
        self.refresh.clicked.connect(self.discover)
        layout.addWidget(self.refresh)
        local_note = QLabel(
            "Port assignments are stored only on this computer:\n"
            f"{local_connections_path()}"
        )
        local_note.setWordWrap(True)
        layout.addWidget(local_note)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        QTimer.singleShot(0, self.discover)

    def port_value(self, box):
        return (
            box.currentData()
            if box.currentIndex() >= 0
            and box.currentText() == box.itemText(box.currentIndex())
            else box.currentText().strip()
        )

    def discover(self):
        if self.worker is not None:
            return
        self.status.setText("Discovering ports…")
        self.refresh.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.worker = DiscoveryWorker(self)
        self.worker.found.connect(self.show_candidates)
        self.worker.finished.connect(self.discovery_finished)
        self.worker.start()

    def show_candidates(self, found):
        serial = found["serial"]
        descriptions = {
            visa_address(p["device"]): f"{p['description']} · {p['device']}"
            for p in serial
        }
        for device, box in self.ports.items():
            current = self.port_value(box)
            box.clear()
            box.addItem("Not configured", "")
            candidates = (
                [p["device"] for p in serial] if device == "shutter" else found["visa"]
            )
            for address in candidates:
                description = next(
                    (p["description"] for p in serial if p["device"] == address),
                    descriptions.get(address, ""),
                )
                box.addItem(
                    f"{address} — {description}" if description else address, address
                )
            index = box.findData(current)
            if index < 0:
                box.addItem(f"{current} — saved / manual address", current)
                index = box.count() - 1
            box.setCurrentIndex(index)
        self.status.setText(
            found["error"]
            or "Discovery complete. Addresses are candidates, not verified devices."
        )

    def discovery_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.refresh.setEnabled(True)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
        if self.closing_after_scan:
            super().reject()

    def reject(self):
        if self.worker is not None:
            self.closing_after_scan = True
            self.status.setText("Finishing port discovery before closing…")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.closing_after_scan = True
            self.status.setText("Finishing port discovery before closing…")
            event.ignore()
        else:
            super().closeEvent(event)

    def validate_and_accept(self):
        values = connection_values(self.config)
        for device, box in self.ports.items():
            address = self.port_value(box)
            if device != "shutter" and (
                address.upper().startswith("COM") or address.startswith("/")
            ):
                address = visa_address(address)
            values[device]["port"] = address
        for device, box in self.bauds.items():
            values[device]["baud_rate"] = box.value()
        for device, box in self.terminations.items():
            values[device]["read_termination"] = box.currentData()
        try:
            apply_connections(self.config, values)
            self.config.hardware.use_mock = self.simulated.isChecked()
            self.config.hardware.shutter.enabled = self.shutter_enabled.isChecked()
            problems = connection_problems(self.config, self.measurement)
            if problems:
                raise ValueError("\n".join(problems))
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.accept()
