"""api layer, module 5 (generated, deterministic)."""

from services.services0 import services0_gamma
from services.services0 import services0_beta


def api5_alpha(value):
    """Leaf computation for api5."""
    return services0_gamma(value) + 1


def api5_beta(value):
    """Doubles the api5 alpha result."""
    return api5_alpha(value) * 2


def api5_gamma(value):
    """Aggregates api5 results."""
    return api5_beta(value) + services0_beta(value)


class Api5Widget:
    """Widget facade over the api5 pipeline."""

    def run(self, value):
        return api5_gamma(value)


def api5_launch(value):
    """Entry point: builds and runs the api5 widget."""
    widget = Api5Widget()
    return widget.run(value)
