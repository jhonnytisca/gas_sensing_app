"""Readable line samples without thickening the actual measurement curves."""

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from pyqtgraph.graphicsItems.LegendItem import ItemSample


class ThickLineSample(ItemSample):
    def paint(self, painter, *args):
        if not self.item.isVisible():
            return super().paint(painter, *args)
        pen = pg.mkPen(self.item.opts["pen"])
        pen.setWidthF(max(1.0, pen.widthF()) * 3)
        if pen.style() == Qt.PenStyle.DashLine:
            # Keep two visible dashes in the short sample despite the wider pen.
            pen.setDashPattern([1.5, 1.2])
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setPen(pen)
        painter.drawLine(0, 11, 20, 11)
