"""
This file contains methods for temperature conversion and a :class:`Temperature`
class, which should be used to wrap temperature data to make it more portable.
"""
#: These can be used to validate units
TEMP_UNITS = {
    'C': 'celcius',
    'F': 'fahrenheit',
    'K': 'kelvin'
}

def degrees_c_to_k(val):
    "Convert degrees celcius to degrees kelvin"
    return val + 273.15

def degrees_k_to_c(val):
    "Convert degrees kelvin to degrees celcius"
    return val - 273.15

def degrees_f_to_c(val):
    "Convert degrees fahrenheit to degrees celcius"
    return (val - 32) * 5/9.0

def degrees_c_to_f(val):
    "Convert degrees celcius to degrees fahrenheit"
    return val * 9/5.0 + 32

def degrees_f_to_k(val):
    "Convert degrees fahrenheit to degrees kelvin"
    return degrees_c_to_k(degrees_f_to_c(val))

def degrees_k_to_f(val):
    "Convert degrees kelvin to degrees fahrenheit"
    return degrees_c_to_f(degrees_k_to_c(val))

class Temperature(object):
    """
    All temperature readings should be implemented with this class, which wraps
    the temp values stored internally and allows them to be output in whatever
    unit the caller specifies. All temperatures are internally stored as degrees
    Kelvin.
    """
    def __init__(self, value, unit='C'):
        "Initialize"
        unit = unit[0].upper()
        if unit == 'C':
            self._value = degrees_c_to_k(value)
        elif unit == 'F':
            self._value = degrees_f_to_k(value)
        elif unit == 'K':
            self._value = value
        else:
            raise ConfigurationError("Temperature units must be in C, K, or F")

    @classmethod
    def from_celcius(cls, value):
        "Initialize a temp object from a celcius value"
        return cls(value, unit='C')

    @classmethod
    def from_fahrenheit(cls, value):
        "Initialize a temp object from a fahrenheit value"
        return cls(value, unit='F')

    @classmethod
    def from_kelvin(cls, value):
        "Initialize a temp object from a kelvin value"
        return cls(value, unit='K')

    def as_unit(self, unit='C'):
        "Return the temp value in the given units"
        unit = unit[0].upper()
        if unit == 'C':
            return self.as_c()
        elif unit == 'F':
            return self.as_f()
        elif unit == 'K':
            return self.as_k()
        raise ConfigurationError("Unit must be C, K, or F")

    def as_c(self):
        "Returns the temperature in Celcius"
        return degrees_k_to_c(self._value)

    def as_f(self):
        "Returns the temperature in fahrenheit"
        return degrees_k_to_f(self._value)

    def as_k(self):
        "Return the temperature in kelvins"
        return self._value

    def __str__(self):
        return "{:.2f} K".format(self._value)

    def __repr__(self):
        return self.__str__()
