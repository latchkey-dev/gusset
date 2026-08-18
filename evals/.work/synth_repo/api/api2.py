"""api layer, module 2 (generated, deterministic)."""

from services.services2 import services2_gamma
from services.services0 import services0_beta


def api2_alpha(value):
    """Leaf computation for api2."""
    return services2_gamma(value) + 1


def api2_beta(value):
    """Doubles the api2 alpha result."""
    return api2_alpha(value) * 2


def api2_gamma(value):
    """Aggregates api2 results."""
    return api2_beta(value) + services0_beta(value)


class Api2Widget:
    """Widget facade over the api2 pipeline."""

    def run(self, value):
        return api2_gamma(value)


def api2_launch(value):
    """Entry point: builds and runs the api2 widget."""
    widget = Api2Widget()
    return widget.run(value)
