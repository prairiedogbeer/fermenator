"""
Houses custom exception classes for fermenator.
"""

class FermenatorError(RuntimeError):
    """
    All custom fermenator exceptions should descend from this one,
    making it easy to catch all fermenator-generate exceptions and
    handle them at once, keeping lower-level OS exceptions separate.
    """
    pass

class StaleDataError(FermenatorError):
    "Raise this error when data appears to be out of date"
    pass

class DataFetchError(FermenatorError):
    "Raise this exception when an error occurs during data fetch operations"
    pass

class ConfigurationError(FermenatorError):
    "Raise this exception when a configuration error is detected"
    pass

class DataValidationError(FermenatorError):
    "Raise this when data is passed in the incorrect format for the method"
    pass

class ClassNotFoundError(FermenatorError):
    """
    Raise this when dynamic class loading is unable to find a class specified
    in configuration
    """
    pass

class ConfigNotFoundError(FermenatorError):
    "Raise this exception when no configuration can be found/loaded"
    pass
