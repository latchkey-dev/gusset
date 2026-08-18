"""api layer, module 3 (generated, deterministic)."""

from services.services0 import services0_gamma
from services.services1 import services1_beta


def api3_alpha(value):
    """Leaf computation for api3."""
    return services0_gamma(value) + 1


def api3_beta(value):
    """Doubles the api3 alpha result."""
    return api3_alpha(value) * 2


def api3_gamma(value):
    """Aggregates api3 results."""
    return api3_beta(value) + services1_beta(value)


class Api3Widget:
    """Widget facade over the api3 pipeline."""

    def run(self, value):
        return api3_gamma(value)


def api3_launch(value):
    """Entry point: builds and runs the api3 widget."""
    widget = Api3Widget()
    return widget.run(value)
