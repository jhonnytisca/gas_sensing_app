import importlib
from enum import Enum
from pathlib import Path

import pyqtgraph as pg

from PyQt6.QtGui import QFontDatabase


class Theme(str, Enum):
    DARK = "dark"
    LIGHT = "light"


STYLE_DIR = Path(__file__).parent.parent.parent / "assets" / "styles"
ICON_DIR = Path(__file__).parent.parent.parent / "assets" / "icons"

DEFAULT_THEME = Theme.DARK

DEFAULT_FONT = QFontDatabase.systemFont(
                                QFontDatabase.SystemFont.FixedFont
                            )

def get_qss_assets(theme: Theme) -> dict[str, Path]:
    """
    Get QSS assets according to theme.
    """
    theme_icon_dir = ICON_DIR / theme.value

    return {
        "@COMBOBOX_ARROW@": theme_icon_dir / "combobox_arrow.svg",
        "@CHECK_ICON@": theme_icon_dir / "check.svg",
        "@SPINBOX_UP@": theme_icon_dir / "spinbox_up.svg",
        "@SPINBOX_DOWN@": theme_icon_dir / "spinbox_down.svg",
    }

def get_pyqtgraph_config(theme: Theme):
    """
    Get pyqtgraph theme configuration
    """
    module = importlib.import_module(f"gas_sensing_app.themes.{theme.value}")

    return module.PYQTGRAPH_CONFIG


def apply_pyqtgraph_theme(theme: Theme):
    """
    Apply default theme for newly created pyqtgraph widgets.
    """
    config = get_pyqtgraph_config(theme)

    for key, value in config.items():
        pg.setConfigOption(key, value)


def update_plot_theme(plot, theme: Theme):
    """
    Update already existing pyqtgraph widget.
    """
    config = get_pyqtgraph_config(theme)

    background = config["background"]
    foreground = config["foreground"]

    # Background
    plot.setBackground(background)
    plot.setTitle(plot.property("title"), color=foreground)

    # Axes
    for axis_name in ("left", "bottom", "right", "top"):
        axis = plot.getAxis(axis_name)

        axis.setPen(foreground)
        axis.setTextPen(foreground)
        
def replace_qss_assets(stylesheet: str, theme: Theme) -> str:
    for placeholder, path in get_qss_assets(theme).items():
        stylesheet = stylesheet.replace(
            placeholder,
            str(path).replace("\\","/")
        )
    return stylesheet


def load_theme(theme: Theme = DEFAULT_THEME) -> str:
    """
    Load QSS and update pyqtgraph default theme.
    """

    apply_pyqtgraph_theme(theme)

    if isinstance(theme, str):
        theme = Theme(theme)

    files = ["base.qss", f"{theme.value}.qss"]

    stylesheet = ""

    for file in files:
        path = STYLE_DIR / file
        if not path.exists():
            print(f"[Error] Failed to load style: {theme.value}")
            continue
        stylesheet += path.read_text() + "\n"

    return replace_qss_assets(stylesheet, theme)

def refresh_style(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
