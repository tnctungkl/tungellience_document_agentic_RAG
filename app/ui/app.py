"""UI entry point.

The production UI is served by FastAPI from app.ui.static. This module is kept
as a discoverable application boundary for tooling and future UI adapters.
"""

from pathlib import Path

UI_INDEX = Path(__file__).resolve().parent / "static" / "index.html"


def get_ui_index() -> Path:
    """Return the absolute path to the production web application's entry point."""
    return UI_INDEX
