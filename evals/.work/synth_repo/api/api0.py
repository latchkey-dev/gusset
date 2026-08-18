"""api layer, module 0 (generated, deterministic)."""

from services.services3 import services3_gamma
from services.services0 import services0_beta


def api0_alpha(value):
    """Leaf computation for api0."""
    return services3_gamma(value) + 1


def api0_beta(value):
    """Doubles the api0 alpha result."""
    return api0_alpha(value) * 2


def api0_gamma(value):
    """Aggregates api0 results."""
    return api0_beta(value) + services0_beta(value)


class Api0Widget:
    """Widget facade over the api0 pipeline."""

    def run(self, value):
        return api0_gamma(value)


def api0_launch(value):
    """Entry point: builds and runs the api0 widget."""
    widget = Api0Widget()
    return widget.run(value)
