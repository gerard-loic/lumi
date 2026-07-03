import os

from lib.config.config import Config

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DEFAULT_COLOR = "1F4E79"


def template_color() -> str:
    return Config.get("pdf.template_color", default=_DEFAULT_COLOR)


def template_logo() -> str | None:
    relative = Config.get("pdf.template_logo", default=None)
    if not relative:
        return None
    path = relative if os.path.isabs(relative) else os.path.join(_ROOT_DIR, relative)
    return path if os.path.exists(path) else None


def template_footer_text() -> str | None:
    return Config.get("pdf.template_footer_text", default=None)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
