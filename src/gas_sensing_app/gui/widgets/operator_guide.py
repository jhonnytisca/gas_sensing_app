"""Searchable in-application guide with images sized to its viewport."""

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QImage, QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


class GuideBrowser(QTextBrowser):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.charFormat().isImageFormat():
                    image_format = fragment.charFormat().toImageFormat()
                    path = self.document().baseUrl().resolved(QUrl(image_format.name()))
                    image = QImage(path.toLocalFile())
                    if not image.isNull():
                        width = min(
                            image.width(), max(100, self.viewport().width() - 40)
                        )
                        image_format.setWidth(width)
                        image_format.setHeight(width * image.height() / image.width())
                        cursor = QTextCursor(self.document())
                        cursor.setPosition(fragment.position())
                        cursor.setPosition(
                            fragment.position() + fragment.length(),
                            QTextCursor.MoveMode.KeepAnchor,
                        )
                        cursor.setCharFormat(image_format)
                iterator += 1
            block = block.next()


class OperatorGuide(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Gas Sensing · Operator guide")
        self.resize(min(900, parent.width()), min(760, parent.height()))
        layout = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a topic, e.g. wiring, recipe or shutdown")
        self.search.setAccessibleName("Find in operator guide")
        next_button = QPushButton("Find next")
        search_row.addWidget(self.search, 1)
        search_row.addWidget(next_button)
        layout.addLayout(search_row)
        self.browser = GuideBrowser()
        self.browser.setOpenExternalLinks(True)
        path = Path(__file__).resolve().parents[2] / "assets/manual/operator-guide.md"
        self.browser.document().setBaseUrl(QUrl.fromLocalFile(str(path.parent) + "/"))
        self.browser.setMarkdown(path.read_text(encoding="utf-8"))
        layout.addWidget(self.browser)
        self.search.returnPressed.connect(self.find_next)
        next_button.clicked.connect(self.find_next)

    def find_next(self):
        if self.search.text() and not self.browser.find(self.search.text()):
            self.browser.moveCursor(QTextCursor.MoveOperation.Start)
            self.browser.find(self.search.text())
