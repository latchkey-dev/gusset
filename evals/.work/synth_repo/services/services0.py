"""services layer, module 0 (generated, deterministic)."""

from domain.domain5 import domain5_gamma
from domain.domain5 import domain5_beta


def services0_alpha(value):
    """Leaf computation for services0."""
    return domain5_gamma(value) + 1


def services0_beta(value):
    """Doubles the services0 alpha result."""
    return services0_alpha(value) * 2


def services0_gamma(value):
    """Aggregates services0 results."""
    return services0_beta(value) + domain5_beta(value)


class Services0Widget:
    """Widget facade over the services0 pipeline."""

    def run(self, value):
        return services0_gamma(value)


def services0_launch(value):
    """Entry point: builds and runs the services0 widget."""
    widget = Services0Widget()
    return widget.run(value)
