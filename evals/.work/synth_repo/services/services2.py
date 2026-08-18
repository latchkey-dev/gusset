"""services layer, module 2 (generated, deterministic)."""

from domain.domain1 import domain1_gamma
from domain.domain1 import domain1_beta


def services2_alpha(value):
    """Leaf computation for services2."""
    return domain1_gamma(value) + 1


def services2_beta(value):
    """Doubles the services2 alpha result."""
    return services2_alpha(value) * 2


def services2_gamma(value):
    """Aggregates services2 results."""
    return services2_beta(value) + domain1_beta(value)


class Services2Widget:
    """Widget facade over the services2 pipeline."""

    def run(self, value):
        return services2_gamma(value)


def services2_launch(value):
    """Entry point: builds and runs the services2 widget."""
    widget = Services2Widget()
    return widget.run(value)
