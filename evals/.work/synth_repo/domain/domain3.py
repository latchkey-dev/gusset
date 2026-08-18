"""domain layer, module 3 (generated, deterministic)."""

from core.core4 import core4_gamma
from core.core1 import core1_beta


def domain3_alpha(value):
    """Leaf computation for domain3."""
    return core4_gamma(value) + 1


def domain3_beta(value):
    """Doubles the domain3 alpha result."""
    return domain3_alpha(value) * 2


def domain3_gamma(value):
    """Aggregates domain3 results."""
    return domain3_beta(value) + core1_beta(value)


class Domain3Widget:
    """Widget facade over the domain3 pipeline."""

    def run(self, value):
        return domain3_gamma(value)


def domain3_launch(value):
    """Entry point: builds and runs the domain3 widget."""
    widget = Domain3Widget()
    return widget.run(value)
