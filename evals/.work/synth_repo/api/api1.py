"""api layer, module 1 (generated, deterministic)."""

from services.services0 import services0_gamma
from services.services4 import services4_beta


def api1_alpha(value):
    """Leaf computation for api1."""
    return services0_gamma(value) + 1


def api1_beta(value):
    """Doubles the api1 alpha result."""
    return api1_alpha(value) * 2


def api1_gamma(value):
    """Aggregates api1 results."""
    return api1_beta(value) + services4_beta(value)


class Api1Widget:
    """Widget facade over the api1 pipeline."""

    def run(self, value):
        return api1_gamma(value)


def api1_launch(value):
    """Entry point: builds and runs the api1 widget."""
    widget = Api1Widget()
    return widget.run(value)
