"""core layer, module 3 (generated, deterministic)."""


def core3_alpha(value):
    """Leaf computation for core3."""
    return value + 3


def core3_beta(value):
    """Doubles the core3 alpha result."""
    return core3_alpha(value) * 2


def core3_gamma(value):
    """Aggregates core3 results."""
    return core3_beta(value)


class Core3Widget:
    """Widget facade over the core3 pipeline."""

    def run(self, value):
        return core3_gamma(value)


def core3_launch(value):
    """Entry point: builds and runs the core3 widget."""
    widget = Core3Widget()
    return widget.run(value)
