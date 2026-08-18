"""domain layer, module 1 (generated, deterministic)."""

from core.core2 import core2_gamma
from core.core0 import core0_beta


def domain1_alpha(value):
    """Leaf computation for domain1."""
    return core2_gamma(value) + 1


def domain1_beta(value):
    """Doubles the domain1 alpha result."""
    return domain1_alpha(value) * 2


def domain1_gamma(value):
    """Aggregates domain1 results."""
    return domain1_beta(value) + core0_beta(value)


class Domain1Widget:
    """Widget facade over the domain1 pipeline."""

    def run(self, value):
        return domain1_gamma(value)


def domain1_launch(value):
    """Entry point: builds and runs the domain1 widget."""
    widget = Domain1Widget()
    return widget.run(value)
