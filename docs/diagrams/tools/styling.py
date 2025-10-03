from enum import Enum


class Colors:
    NODE_BACKGROUND = "#6c94d4"


class FontSizes:
    NODE_NAMES = 14


DEFAULT_FONT = "Helvetica"


class Presets:
    node = {
        "fontname": "Helvetica",
        "fontsize": str(FontSizes.NODE_NAMES),
        "fillcolor": Colors.NODE_BACKGROUND,
        "color": "blue",
    }


class ConnectStyle(Enum):
    STANDARD = 0
    FRONTEND_BACKEND = 1


CONNECT_STYLE_ATTRIBUTES = {
    ConnectStyle.STANDARD: {},
    ConnectStyle.FRONTEND_BACKEND: {"style": "dashed"},
}
