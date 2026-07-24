from __future__ import annotations

import sysconfig
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def pytest_report_header(config: pytest.Config) -> list[str]:  # ruff: ignore[unused-function-argument]
    """Return a list of strings to be displayed in the header of the report."""
    is_freethreaded = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))

    return [
        f"Free-threaded: {is_freethreaded}",
    ]
