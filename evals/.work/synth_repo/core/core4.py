"""core layer, module 4 (generated, deterministic)."""


def core4_alpha(value):
    """Leaf computation for core4."""
    return value + 4


def core4_beta(value):
    """Doubles the core4 alpha result."""
    return core4_alpha(value) * 2


def core4_gamma(value):
    """Aggregates core4 results."""
    return core4_beta(value)


class Core4Widget:
    """Widget facade over the core4 pipeline."""

    def run(self, value):
        return core4_gamma(value)


def core4_launch(value):
    """Entry point: builds and runs the core4 widget."""
    widget = Core4Widget()
    return widget.run(value)
