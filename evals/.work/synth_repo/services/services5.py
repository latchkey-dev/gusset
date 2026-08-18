"""services layer, module 5 (generated, deterministic)."""

from domain.domain0 import domain0_gamma
from domain.domain5 import domain5_beta


def services5_alpha(value):
    """Leaf computation for services5."""
    return domain0_gamma(value) + 1


def services5_beta(value):
    """Doubles the services5 alpha result."""
    return services5_alpha(value) * 2


def services5_gamma(value):
    """Aggregates services5 results."""
    return services5_beta(value) + domain5_beta(value)


class Services5Widget:
    """Widget facade over the services5 pipeline."""

    def run(self, value):
        return services5_gamma(value)


def services5_launch(value):
    """Entry point: builds and runs the services5 widget."""
    widget = Services5Widget()
    return widget.run(value)
