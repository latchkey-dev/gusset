from pkg import lib
from pkg.models import Child


def main():
    result = lib.helper(1)
    child = Child()
    return result, child.describe()
