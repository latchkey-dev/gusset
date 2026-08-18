"""api layer, module 4 (generated, deterministic)."""

from services.services5 import services5_gamma
from services.services0 import services0_beta


def api4_alpha(value):
    """Leaf computation for api4."""
    return services5_gamma(value) + 1


def api4_beta(value):
    """Doubles the api4 alpha result."""
    return api4_alpha(value) * 2


def api4_gamma(value):
    """Aggregates api4 results."""
    return api4_beta(value) + services0_beta(value)


class Api4Widget:
    """Widget facade over the api4 pipeline."""

    def run(self, value):
        return api4_gamma(value)


def api4_launch(value):
    """Entry point: builds and runs the api4 widget."""
    widget = Api4Widget()
    return widget.run(value)
