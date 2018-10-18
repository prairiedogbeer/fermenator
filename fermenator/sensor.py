"""
Sensors are any source of data about a Fermenter. They may be hardware
temperature sensors, or a wrapper around data collected out-of-band and
stored in a database. The sky is the limit.

The point of having Sensor classes is to abstract the lower layer
datasource, and to provide some common intelligence/APIs around sensor
readings, such as maintining moving averages, performing validations,
etc.
"""
import time
import logging
import datetime
import collections
from .exception import (
    StaleDataError, ConfigurationError, DataFetchError,
    InvalidTemperatureError, DataSourceError)
from .temperature import Temperature, TEMP_UNITS

class Sensor(object):
    """
    This is the abstract base class for all Sensor objects.

    Sensor readings are averaged together in a weighted moving average, where
    the weight of the most recent reading is equivalent to the number of points
    averaged together (eg. if moving_average_size is set to 10, the most
    recent point will get a weight of ten, the previous will get a weight of 9,
    and so on).

    Pass in a name and any of the following kwargs:

    - moving_average_size: optional, number of data points to average
      [default: 10]
    """
    def __init__(self, name, **kwargs):
        """
        Initialize the class
        """
        self.name = name
        self._args = kwargs
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self.name))
        self.moving_average_size = int(kwargs.pop('moving_average_size', 10))
        self._readings = collections.deque(
            [None]*self.moving_average_size, self.moving_average_size)
        self._moving_avg_val = None

    def fetch(self):
        """
        Returns the current value from the sensor. This method should call
        :meth:`_add_value` to ensure that moving average and reading history
        are updated. It is up to the implementation to decide whether or not
        the raw sensor value or a moving average value are returned. Further,
        the implementation should call :meth:`_add_value` so that
        the other fetch methods work properly.
        """
        pass

    def fetch_last(self):
        """Returns the most recently fetched value from the sensor. By default,
        that will be the moving average value. Override in subclass if you want
        to pass back a different value"""
        return self._moving_avg_val

    def _add_value(self, value):
        """
        Updates the moving average and readings history.
        """
        self._readings.append(value)
        if self._moving_avg_val is None:
            self._moving_avg_val = value
        else:
            denom = 0
            numerator = 0
            for reading in range(self.moving_average_size, 0, -1):
                if self._readings[reading - 1] is None:
                    break
                numerator += reading * self._readings[reading -1]
                denom += reading
            self._moving_avg_val = numerator / float(denom)

class TempSensor(Sensor):
    """
    Base class for all temperature sensor objects. Adds convenience methods
    around managing temperature units. The individual class implementations
    should deal with temperature conversions on the data storage side, but
    the user should be able to set the `units` kwarg to C, K, or F to
    specify what unit the data returned by the class should be in.
    """
    def __init__(self, name, **kwargs):
        "Initialize"
        super(self, TempSensor).__init__(name, **kwargs)
        try:
            units = TEMP_UNITS[kwargs.pop('units', 'C')[0].upper()]
        except KeyError:
            raise ConfigurationError("Temp units must be C, K, or F")
