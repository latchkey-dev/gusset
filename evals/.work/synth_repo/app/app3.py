"""app layer, module 3 (generated, deterministic)."""

from api.api0 import api0_gamma
from api.api4 import api4_beta


def app3_alpha(value):
    """Leaf computation for app3."""
    return api0_gamma(value) + 1


def app3_beta(value):
    """Doubles the app3 alpha result."""
    return app3_alpha(value) * 2


def app3_gamma(value):
    """Aggregates app3 results."""
    return app3_beta(value) + api4_beta(value)


class App3Widget:
    """Widget facade over the app3 pipeline."""

    def run(self, value):
        return app3_gamma(value)


def app3_launch(value):
    """Entry point: builds and runs the app3 widget."""
    widget = App3Widget()
    return widget.run(value)
