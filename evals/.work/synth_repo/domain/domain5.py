"""domain layer, module 5 (generated, deterministic)."""

from core.core5 import core5_gamma
from core.core1 import core1_beta


def domain5_alpha(value):
    """Leaf computation for domain5."""
    return core5_gamma(value) + 1


def domain5_beta(value):
    """Doubles the domain5 alpha result."""
    return domain5_alpha(value) * 2


def domain5_gamma(value):
    """Aggregates domain5 results."""
    return domain5_beta(value) + core1_beta(value)


class Domain5Widget:
    """Widget facade over the domain5 pipeline."""

    def run(self, value):
        return domain5_gamma(value)


def domain5_launch(value):
    """Entry point: builds and runs the domain5 widget."""
    widget = Domain5Widget()
    return widget.run(value)
