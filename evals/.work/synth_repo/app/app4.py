"""app layer, module 4 (generated, deterministic)."""

from api.api1 import api1_gamma
from api.api0 import api0_beta


def app4_alpha(value):
    """Leaf computation for app4."""
    return api1_gamma(value) + 1


def app4_beta(value):
    """Doubles the app4 alpha result."""
    return app4_alpha(value) * 2


def app4_gamma(value):
    """Aggregates app4 results."""
    return app4_beta(value) + api0_beta(value)


class App4Widget:
    """Widget facade over the app4 pipeline."""

    def run(self, value):
        return app4_gamma(value)


def app4_launch(value):
    """Entry point: builds and runs the app4 widget."""
    widget = App4Widget()
    return widget.run(value)
