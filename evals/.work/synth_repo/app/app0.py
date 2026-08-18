"""app layer, module 0 (generated, deterministic)."""

from api.api4 import api4_gamma
from api.api5 import api5_beta


def app0_alpha(value):
    """Leaf computation for app0."""
    return api4_gamma(value) + 1


def app0_beta(value):
    """Doubles the app0 alpha result."""
    return app0_alpha(value) * 2


def app0_gamma(value):
    """Aggregates app0 results."""
    return app0_beta(value) + api5_beta(value)


class App0Widget:
    """Widget facade over the app0 pipeline."""

    def run(self, value):
        return app0_gamma(value)


def app0_launch(value):
    """Entry point: builds and runs the app0 widget."""
    widget = App0Widget()
    return widget.run(value)
