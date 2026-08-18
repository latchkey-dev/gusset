"""core layer, module 2 (generated, deterministic)."""


def core2_alpha(value):
    """Leaf computation for core2."""
    return value + 2


def core2_beta(value):
    """Doubles the core2 alpha result."""
    return core2_alpha(value) * 2


def core2_gamma(value):
    """Aggregates core2 results."""
    return core2_beta(value)


class Core2Widget:
    """Widget facade over the core2 pipeline."""

    def run(self, value):
        return core2_gamma(value)


def core2_launch(value):
    """Entry point: builds and runs the core2 widget."""
    widget = Core2Widget()
    return widget.run(value)
