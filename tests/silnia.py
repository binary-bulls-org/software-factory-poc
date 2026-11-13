def silnia(n):
    import operator
    from functools import reduce
    return reduce(operator.mul, range(1, n + 1), 1)