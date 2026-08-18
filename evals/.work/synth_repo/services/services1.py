"""services layer, module 1 (generated, deterministic)."""

from domain.domain5 import domain5_gamma
from domain.domain1 import domain1_beta


def services1_alpha(value):
    """Leaf computation for services1."""
    return domain5_gamma(value) + 1


def services1_beta(value):
    """Doubles the services1 alpha result."""
    return services1_alpha(value) * 2


def services1_gamma(value):
    """Aggregates services1 results."""
    return services1_beta(value) + domain1_beta(value)


class Services1Widget:
    """Widget facade over the services1 pipeline."""

    def run(self, value):
        return services1_gamma(value)


def services1_launch(value):
    """Entry point: builds and runs the services1 widget."""
    widget = Services1Widget()
    return widget.run(value)
