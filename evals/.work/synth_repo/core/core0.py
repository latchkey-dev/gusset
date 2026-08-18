"""core layer, module 0 (generated, deterministic)."""


def core0_alpha(value):
    """Leaf computation for core0."""
    return value + 0


def core0_beta(value):
    """Doubles the core0 alpha result."""
    return core0_alpha(value) * 2


def core0_gamma(value):
    """Aggregates core0 results."""
    return core0_beta(value)


class Core0Widget:
    """Widget facade over the core0 pipeline."""

    def run(self, value):
        return core0_gamma(value)


def core0_launch(value):
    """Entry point: builds and runs the core0 widget."""
    widget = Core0Widget()
    return widget.run(value)
