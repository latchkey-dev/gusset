"""services layer, module 6 (generated, deterministic)."""

from domain.domain2 import domain2_gamma
from domain.domain3 import domain3_beta


def services6_alpha(value):
    """Leaf computation for services6."""
    return domain2_gamma(value) + 1


def services6_beta(value):
    """Doubles the services6 alpha result."""
    return services6_alpha(value) * 2


def services6_gamma(value):
    """Aggregates services6 results."""
    return services6_beta(value) + domain3_beta(value)


class Services6Widget:
    """Widget facade over the services6 pipeline."""

    def run(self, value):
        return services6_gamma(value)


def services6_launch(value):
    """Entry point: builds and runs the services6 widget."""
    widget = Services6Widget()
    return widget.run(value)
