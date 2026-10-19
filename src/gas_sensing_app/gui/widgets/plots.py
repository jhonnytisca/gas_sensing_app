"""Four time-linked plots with bounded live history per sensor."""

import importlib
import math
from collections import deque

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter

from gas_sensing_app.gui.styles.theme_manager import DEFAULT_THEME, update_plot_theme


class MeasurementPlots(QSplitter):
    def __init__(self, gas_names, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.gas_names = gas_names
        self.theme = DEFAULT_THEME
        self.labels = {}
        self.plots = {}
        self.curves = {}
        self.history = {}
        for key, title, unit in (
            ("resistance_ohm", "Resistance", "Ω"),
            ("voltage_V", "Voltage", "V"),
            ("current_A", "Current", "A"),
            ("flows", "Gas flows", "sccm"),
        ):
            plot = pg.PlotWidget()
            plot.setProperty("title", title)
            plot.setTitle(title, size="11pt")
            plot.setLabel("left", title, units=unit)
            plot.getAxis("left").setWidth(85)
            if key == "flows":
                plot.setLabel("bottom", "Elapsed time", units="s")
            else:
                plot.getAxis("bottom").setStyle(showValues=False)
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.addLegend(colCount=2, offset=(8, 8), labelTextSize="8pt")
            plot.setMinimumHeight(150)
            self.plots[key] = plot
            self.addWidget(plot)
        for key, plot in self.plots.items():
            if key != "flows":
                plot.setXLink(self.plots["flows"])
        self.setChildrenCollapsible(False)
        self.setSizes([200] * 4)
        self.apply_theme(DEFAULT_THEME)

    def clear(self):
        for plot in self.plots.values():
            plot.clear()
            plot.plotItem.legend.clear()
        self.curves.clear()
        self.history.clear()
        self.labels.clear()
        self.fit()

    def append(self, data):
        values = [
            (key, data["device"], data[key])
            for key in ("resistance_ohm", "voltage_V", "current_A")
        ]
        values += [
            ("flows", self.gas_names[ch], value) for ch, value in data["flows"].items()
        ]
        if data["gate_setpoint_V"] is not None:
            values += [
                ("voltage_V", "Gate setpoint", data["gate_setpoint_V"]),
                ("voltage_V", "Gate readback", data["gate_voltage_V"]),
            ]
        for key, label, value in values:
            identity = (key, label)
            if identity not in self.curves:
                if label not in self.labels:
                    self.labels[label] = len(self.labels)
                color = self.curve_color(label)
                self.curves[identity] = self.plots[key].plot(
                    name=label.replace("_", " "),
                    pen=self.curve_pen(label, color),
                    connect="finite",
                )
                count = sum(1 for curve_key, _ in self.curves if curve_key == key)
                self.plots[key].setMinimumHeight(max(160, 95 + ((count + 1) // 2) * 22))
                self.history[identity] = (deque(maxlen=10000), deque(maxlen=10000))
            times, samples = self.history[identity]
            times.append(data["elapsed_s"])
            samples.append(value if value is not None else math.nan)
            self.curves[identity].setData(list(times), list(samples))

    def curve_color(self, label):
        palette = importlib.import_module(
            f"gas_sensing_app.themes.{self.theme.value}"
        ).CURVE_COLORS
        return palette[self.labels[label] % len(palette)]

    def curve_pen(self, label, color):
        return pg.mkPen(
            color,
            width=1.8,
            style=(
                Qt.PenStyle.DashLine
                if label == "Gate setpoint"
                else Qt.PenStyle.SolidLine
            ),
        )

    def apply_theme(self, theme):
        self.theme = theme
        for plot in self.plots.values():
            update_plot_theme(plot, theme)
        for (_, label), curve in self.curves.items():
            curve.setPen(self.curve_pen(label, self.curve_color(label)))

    def fit(self):
        for plot in self.plots.values():
            plot.enableAutoRange()
