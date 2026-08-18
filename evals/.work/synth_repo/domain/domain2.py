"""domain layer, module 2 (generated, deterministic)."""

from core.core5 import core5_gamma
from core.core0 import core0_beta


def domain2_alpha(value):
    """Leaf computation for domain2."""
    return core5_gamma(value) + 1


def domain2_beta(value):
    """Doubles the domain2 alpha result."""
    return domain2_alpha(value) * 2


def domain2_gamma(value):
    """Aggregates domain2 results."""
    return domain2_beta(value) + core0_beta(value)


class Domain2Widget:
    """Widget facade over the domain2 pipeline."""

    def run(self, value):
        return domain2_gamma(value)


def domain2_launch(value):
    """Entry point: builds and runs the domain2 widget."""
    widget = Domain2Widget()
    return widget.run(value)
