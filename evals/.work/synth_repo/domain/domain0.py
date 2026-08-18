"""domain layer, module 0 (generated, deterministic)."""

from core.core5 import core5_gamma
from core.core0 import core0_beta


def domain0_alpha(value):
    """Leaf computation for domain0."""
    return core5_gamma(value) + 1


def domain0_beta(value):
    """Doubles the domain0 alpha result."""
    return domain0_alpha(value) * 2


def domain0_gamma(value):
    """Aggregates domain0 results."""
    return domain0_beta(value) + core0_beta(value)


class Domain0Widget:
    """Widget facade over the domain0 pipeline."""

    def run(self, value):
        return domain0_gamma(value)


def domain0_launch(value):
    """Entry point: builds and runs the domain0 widget."""
    widget = Domain0Widget()
    return widget.run(value)
