from pathlib import Path
from config import settings


def output_path(filename: str) -> Path:
    return Path(settings.output_dir) / filename


def screenshot_path(filename: str) -> Path:
    return Path(settings.screenshot_dir) / filename
