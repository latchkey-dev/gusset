"""core layer, module 1 (generated, deterministic)."""


def core1_alpha(value):
    """Leaf computation for core1."""
    return value + 1


def core1_beta(value):
    """Doubles the core1 alpha result."""
    return core1_alpha(value) * 2


def core1_gamma(value):
    """Aggregates core1 results."""
    return core1_beta(value)


class Core1Widget:
    """Widget facade over the core1 pipeline."""

    def run(self, value):
        return core1_gamma(value)


def core1_launch(value):
    """Entry point: builds and runs the core1 widget."""
    widget = Core1Widget()
    return widget.run(value)
