"""app layer, module 1 (generated, deterministic)."""

from api.api0 import api0_gamma
from api.api2 import api2_beta


def app1_alpha(value):
    """Leaf computation for app1."""
    return api0_gamma(value) + 1


def app1_beta(value):
    """Doubles the app1 alpha result."""
    return app1_alpha(value) * 2


def app1_gamma(value):
    """Aggregates app1 results."""
    return app1_beta(value) + api2_beta(value)


class App1Widget:
    """Widget facade over the app1 pipeline."""

    def run(self, value):
        return app1_gamma(value)


def app1_launch(value):
    """Entry point: builds and runs the app1 widget."""
    widget = App1Widget()
    return widget.run(value)
