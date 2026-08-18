"""domain layer, module 4 (generated, deterministic)."""

from core.core4 import core4_gamma
from core.core1 import core1_beta


def domain4_alpha(value):
    """Leaf computation for domain4."""
    return core4_gamma(value) + 1


def domain4_beta(value):
    """Doubles the domain4 alpha result."""
    return domain4_alpha(value) * 2


def domain4_gamma(value):
    """Aggregates domain4 results."""
    return domain4_beta(value) + core1_beta(value)


class Domain4Widget:
    """Widget facade over the domain4 pipeline."""

    def run(self, value):
        return domain4_gamma(value)


def domain4_launch(value):
    """Entry point: builds and runs the domain4 widget."""
    widget = Domain4Widget()
    return widget.run(value)
