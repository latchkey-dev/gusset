"""app layer, module 2 (generated, deterministic)."""

from api.api1 import api1_gamma
from api.api0 import api0_beta


def app2_alpha(value):
    """Leaf computation for app2."""
    return api1_gamma(value) + 1


def app2_beta(value):
    """Doubles the app2 alpha result."""
    return app2_alpha(value) * 2


def app2_gamma(value):
    """Aggregates app2 results."""
    return app2_beta(value) + api0_beta(value)


class App2Widget:
    """Widget facade over the app2 pipeline."""

    def run(self, value):
        return app2_gamma(value)


def app2_launch(value):
    """Entry point: builds and runs the app2 widget."""
    widget = App2Widget()
    return widget.run(value)
