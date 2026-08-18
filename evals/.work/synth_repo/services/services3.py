"""services layer, module 3 (generated, deterministic)."""

from domain.domain4 import domain4_gamma
from domain.domain4 import domain4_beta


def services3_alpha(value):
    """Leaf computation for services3."""
    return domain4_gamma(value) + 1


def services3_beta(value):
    """Doubles the services3 alpha result."""
    return services3_alpha(value) * 2


def services3_gamma(value):
    """Aggregates services3 results."""
    return services3_beta(value) + domain4_beta(value)


class Services3Widget:
    """Widget facade over the services3 pipeline."""

    def run(self, value):
        return services3_gamma(value)


def services3_launch(value):
    """Entry point: builds and runs the services3 widget."""
    widget = Services3Widget()
    return widget.run(value)
