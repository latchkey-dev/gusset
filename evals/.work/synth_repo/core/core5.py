"""core layer, module 5 (generated, deterministic)."""


def core5_alpha(value):
    """Leaf computation for core5."""
    return value + 5


def core5_beta(value):
    """Doubles the core5 alpha result."""
    return core5_alpha(value) * 2


def core5_gamma(value):
    """Aggregates core5 results."""
    return core5_beta(value)


class Core5Widget:
    """Widget facade over the core5 pipeline."""

    def run(self, value):
        return core5_gamma(value)


def core5_launch(value):
    """Entry point: builds and runs the core5 widget."""
    widget = Core5Widget()
    return widget.run(value)
