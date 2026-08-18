def helper(x):
    return _internal(x) + 1


def _internal(x):
    return x * 2


def unused_fn():
    return "never called"
