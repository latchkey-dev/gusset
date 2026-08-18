"""services layer, module 4 (generated, deterministic)."""

from domain.domain3 import domain3_gamma
from domain.domain3 import domain3_beta


def services4_alpha(value):
    """Leaf computation for services4."""
    return domain3_gamma(value) + 1


def services4_beta(value):
    """Doubles the services4 alpha result."""
    return services4_alpha(value) * 2


def services4_gamma(value):
    """Aggregates services4 results."""
    return services4_beta(value) + domain3_beta(value)


class Services4Widget:
    """Widget facade over the services4 pipeline."""

    def run(self, value):
        return services4_gamma(value)


def services4_launch(value):
    """Entry point: builds and runs the services4 widget."""
    widget = Services4Widget()
    return widget.run(value)
