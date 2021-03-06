"""
The classes in fermenator.beer model fermentation profiles and apply them to
a given batch of beer, implementing a simple API where a caller may ask,
"do you require heating or cooling?", and the beer responds with True or False.
Based on this simple API, a :class:`fermenator.manager.ManagerThread` may
manage the beer and activate heating or cooling as required.

An additonal aspect of fermenator beers is that they check the recency of their
data, and are capable of logging errors or warnings if the data is old or looks
unreliable.
"""
import time
import logging
import datetime
import collections
from .exception import (
    StaleDataError, ConfigurationError, DataFetchError,
    InvalidTemperatureError, DataSourceError)

class AbstractBeer(object):
    """
    Represents beer sitting in a fermenter or other temperature-controlled
    vessel. The primary purpose of this class is to implement functions that
    determine if the beer needs heating or cooling. This class is designed
    to be subclassed for specific recipes such that fermentation algorithms
    can be programmed.
    """

    def __init__(self, name, **kwargs):
        """
        Default kwargs for all beers:

        - data_age_warning_time (seconds, warn when data is older than this)
        - gravity_unit (optional, defaults to 'P', plato)
        - temperature_unit (optional, defaults to 'C', celcius)
        """
        self._name = name.upper().strip()
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self._name))
        self.data_age_warning_time = float(kwargs.pop(
            'data_age_warning_time', 60 * 3))
        self.gravity_unit = kwargs.pop('gravity_unit', 'P')
        self.temperature_unit = kwargs.pop('temperature_unit', 'C')

    def __del__(self):
        self.log.debug("destructing")

    @property
    def name(self):
        """
        Hiding the name of the beer so that it is read-only after instantiation
        """
        return self._name

    def requires_heating(self, heating_state, cooling_state):
        """Implement this method in a subclass using the algorithm of your choice
        heating_state and cooling_state are boolean values representing whether
        a beer is currently being heated or cooled, which influences the
        set point of the system.
        """
        pass

    def requires_cooling(self, heating_state, cooling_state):
        """Implement this method in a subclass using the algorithm of your choice
        heating_state and cooling_state are boolean values representing whether
        a beer is currently being heated or cooled, which influences the
        set point of the system."""
        pass

    def check_timestamp(self, timestamp):
        """
        Pass a datetime timestamp to this function, it will return True if the date is
        older than the configured :attr:`data_age_warning_time`.
        """
        delta = datetime.datetime.now() - timestamp
        if delta.total_seconds() >= self.data_age_warning_time:
            raise StaleDataError(
                "no data for {} since {}".format(
                    self.name,
                    timestamp.strftime('%Y-%m-%d %H:%M:%S')))

class NoOpBeer(AbstractBeer):
    """
    This beer always reports that no heating or cooling is required. Assign
    this type of beer to a fermentor that is empty or being cleaned.
    """
    def requires_heating(self, heating_state, cooling_state):
        "Always returns false"
        return False

    def requires_cooling(self, heating_state, cooling_state):
        "Always returns false"
        return False

class SetPointBeer(AbstractBeer):
    """
    This version of :class:`AbstractBeer` implements a "dumb" set-point
    approach like you'd find on an STC-1000, with basic hysteresis. Temperature
    readings are averaged together in a weighted moving average, where the
    weight of the most recent reading is equivalent to the number of points
    averaged together (eg. if moving_average_size is set to 10, the most
    recent point will get a weight of ten, the previous will get a weight of 9,
    and so on).
    """

    def __init__(self, name, **kwargs):
        """
        kwargs can include the following:

        - read_datasource (object)
        - identifier (the identifier used at the datasource for this beer)
        - set_point (float)
        - tolerance (optional, in the same units as the beer)
        - data_age_warning_time (optional, in seconds)
        - gravity_unit (optional, defaults to 'P', plato)
        - temperature_unit (optional, defaults to 'C', celcius)
        - moving_average_size: optional, number of temperature points to average
          [default: 10]
        - max_temp_value: optional, temp readings above this value will result
          in errors [default: 35.0]
        - min_temp_value: optional, temp readings below this value will result
          in errors [default: -5.0]
        """
        super(SetPointBeer, self).__init__(name, **kwargs)
        try:
            self.read_datasource = kwargs.pop('read_datasource')
        except KeyError:
            raise ConfigurationError("read_datasource is required in kwargs")
        try:
            self.identifier = kwargs.pop('identifier')
        except KeyError:
            raise ConfigurationError("no identifier specified in beer config")
        try:
            self.set_point = float(kwargs.pop('set_point'))
        except KeyError:
            raise ConfigurationError("no set_point in kwargs")
        self.tolerance = float(kwargs.pop('tolerance', 0.5))
        self.moving_average_size = int(kwargs.pop('moving_average_size', 10))
        self.max_temp_value = float(kwargs.pop('max_temp_value', 35.0))
        self.min_temp_value = float(kwargs.pop('min_temp_value', -5.0))
        self._temp_readings = collections.deque(
            [None]*self.moving_average_size, self.moving_average_size)
        self._moving_avg_temp = None

    def avg_temp(self):
        "Returns the locally cached version of the moving average temperature"
        return self._moving_avg_temp

    def _get_temperature(self, retries=3):
        "Get the current temperature of the beer, log error if old"
        for _ in range(0, retries):
            try:
                data = self.read_datasource.get_temperature(
                    self.identifier)
                if (data['temperature'] > self.max_temp_value) or \
                    (data['temperature'] < self.min_temp_value):
                    raise InvalidTemperatureError(
                        "temperature {} doesn't appear to be valid".format(
                            data['temperature']))
                self.check_timestamp(data['timestamp'])
                self._add_temp(data['temperature'])
                return data['temperature']
            except DataSourceError as err:
                self.log.warning(err)
            time.sleep(5.0)
        raise DataFetchError(
            "unable to fetch temperature from read_datasource after {} tries".format(
                retries))

    def _add_temp(self, temp):
        """
        Updates the moving average and readings history.
        """
        self._temp_readings.append(temp)
        if self._moving_avg_temp is None:
            self._moving_avg_temp = temp
        else:
            denom = 0
            numerator = 0
            for reading in range(self.moving_average_size, 0, -1):
                if self._temp_readings[reading - 1] is None:
                    break
                numerator += reading * self._temp_readings[reading -1]
                denom += reading
            self._moving_avg_temp = numerator / float(denom)

    def requires_heating(self, heating_state, cooling_state):
        """
        Returns True if the beer requires heating based on the set point,
        current temperature, and configured tolerance, False otherwise. If
        data is older than the configured :attr:`data_age_warning_time`,
        returns False, ensuring that the beer is not accidentally heated.

        heating_state and cooling_state are boolean values representing whether
        a beer is currently being heated or cooled, which influences the
        set point of the system.
        """
        if self.set_point is None:
            return False
        temp = self._get_temperature()
        set_point = self.set_point - self.tolerance
        if heating_state:
            set_point = self.set_point
        if self._moving_avg_temp < set_point:
            self.log.info(
                "heating required (t_now=%.1f, t_avg=%.1f t_target=%.1f "
                "t_set_point=%.1f, tolerance=%.2f)",
                temp, self._moving_avg_temp, self.set_point, set_point,
                self.tolerance)
            return True

    def requires_cooling(self, heating_state, cooling_state):
        """
        Returns True if the beer is warmer than the set point by more than
        the configured tolerance, False otherwise.

        heating_state and cooling_state are boolean values representing whether
        a beer is currently being heated or cooled, which influences the
        set point of the system.
        """
        if self.set_point is None:
            return False
        temp = self._get_temperature()
        set_point = self.set_point + self.tolerance
        if cooling_state:
            set_point = self.set_point
        if self._moving_avg_temp > set_point:
            self.log.info(
                "cooling required (t_now=%.1f, t_avg=%.1f t_target=%.1f "
                "t_set_point=%.1f, tolerance=%.2f)",
                temp, self._moving_avg_temp, self.set_point, set_point,
                self.tolerance)
            return True
        return False

class LinearBeer(AbstractBeer):
    """
    Based on a starting and final gravity values, as well as a starting and
    an ending temperature, linearly ramp temperature on a slope.

    For example, a beer starts at 25 plato and should finish at 5 plato,
    for a 20 plato apparent attenuation. The brewmaster wants the beer to start
    at 16 celcius and finish out at 20 celcius, for a 4 degree spread. On day 0,
    with the beer at 25P, the beer will be held at 16 celcius. When the beer
    reaches 20P, 1/4 of planned attenuation, it will be held at 17 celcius.
    As the beer hits 15P, half way to attenuation, it will be at 18 celicus.

    If the beer starts at a higher gravity than anticipated, the configured lower
    starting point temperature will be applied. Same in the reverse direction. Thus,
    at the end of fermentation, this class will behave more or less like a
    :class:`SetPointBeer`.

    .. note::

        Nothing about this class requires that start_set_point is a lower temperature
        than end_set_point. If you want to cool a beer during the course of
        fermentation, go for it.
    """

    def __init__(self, name, **kwargs):
        """
        Supports the following additional kwargs:

        - read_datasource
        - original_gravity (in Plato or SG depending on gravity_unit)
        - final_gravity (in Plato or SG)
        - start_set_point (where to start the beer)
        - end_set_point (where to finish the beer)
        - tolerance (optional, defaults to 0.5 degrees)
        - max_temp_value: optional, raise errors when temp goes above this
          [default: 35]
        - min_temp_value: optional, raise errors when temp falls below this
          [default: -5]
        - moving_average_size: optional, number of temperature/gravity points to
          average [default: 10]
        """
        super(LinearBeer, self).__init__(name, **kwargs)
        try:
            self.read_datasource = kwargs.pop('read_datasource')
        except KeyError:
            raise ConfigurationError("read_datasource is required in kwargs")
        try:
            self.identifier = kwargs.pop('identifier')
        except KeyError:
            raise ConfigurationError("no identifier specified in beer config")
        try:
            self.original_gravity = float(kwargs.pop('original_gravity'))
        except KeyError:
            raise ConfigurationError("original_gravity must be specified")
        try:
            self.final_gravity = float(kwargs.pop('final_gravity'))
        except KeyError:
            raise ConfigurationError("final_gravity must be specified")
        try:
            self.start_set_point = float(kwargs.pop('start_set_point'))
        except KeyError:
            raise ConfigurationError("start_set_point must be specified")
        try:
            self.end_set_point = float(kwargs.pop('end_set_point'))
        except KeyError:
            raise ConfigurationError("end_set_point must be specified")
        self.tolerance = float(kwargs.pop('tolerance', 0.5))
        self.max_temp_value = float(kwargs.pop('max_temp_value', 35.0))
        self.min_temp_value = float(kwargs.pop('min_temp_value', -5.0))
        self.moving_average_size = int(kwargs.pop('moving_average_size', 10))
        self._temp_readings = collections.deque(
            [None]*self.moving_average_size, self.moving_average_size)
        self._moving_avg_temp = None
        self._grav_readings = collections.deque(
            [None]*self.moving_average_size, self.moving_average_size)
        self._moving_avg_grav = None

    def avg_temp(self):
        "Returns the locally cached version of the moving average temperature"
        return self._moving_avg_temp

    def _get_temperature(self, retries=3):
        """
        Get temeperature data from the read_datasource
        """
        for _ in range(0, retries):
            try:
                data = self.read_datasource.get_temperature(self.identifier)
                if (data['temperature'] > self.max_temp_value) or \
                    (data['temperature'] < self.min_temp_value):
                    raise InvalidTemperatureError(
                        "temperature {} doesn't appear to be valid".format(
                            data['temperature']
                        )
                    )
                self.check_timestamp(data['timestamp'])
                self._add_temp(data['temperature'])
                return data['temperature']
            except DataSourceError as err:
                # Allow this error to pass so that we can retry
                self.log.warning(err)
            time.sleep(5.0)
        raise DataFetchError(
            "unable to fetch temperature from read_datasource after {} tries".format(
                retries))

    def _add_temp(self, temp):
        """
        Updates the moving average and readings history.
        """
        self._temp_readings.append(temp)
        if self._moving_avg_temp is None:
            self._moving_avg_temp = temp
        else:
            denom = 0
            numerator = 0
            for reading in range(self.moving_average_size, 0, -1):
                if self._temp_readings[reading - 1] is None:
                    break
                numerator += reading * self._temp_readings[reading -1]
                denom += reading
            self._moving_avg_temp = numerator / float(denom)

    def _get_gravity(self, retries=3):
        """
        Get gravity data from the read_datasource
        """
        for _ in range(0, retries):
            try:
                data = self.read_datasource.get_gravity(self.identifier)
                self.check_timestamp(data['timestamp'])
                self._add_grav(data['gravity'])
                return data['gravity']
            except DataSourceError as err:
                self.log.warning(err)
            time.sleep(5.0)
        raise DataFetchError(
            "unable to fetch gravity from read_datasource after {} tries".format(
                retries))

    def _add_grav(self, grav):
        """
        Updates the moving average and readings history.
        """
        self._grav_readings.append(grav)
        if self._moving_avg_grav is None:
            self._moving_avg_grav = grav
        else:
            denom = 0
            numerator = 0
            for reading in range(self.moving_average_size, 0, -1):
                if self._grav_readings[reading - 1] is None:
                    break
                numerator += reading * self._grav_readings[reading -1]
                denom += reading
            self._moving_avg_grav = numerator / float(denom)

    def requires_heating(self, heating_state, cooling_state):
        gravity = self._get_gravity()
        current_temp = self._get_temperature()
        progress = self.calc_progress(self._moving_avg_grav)
        target = self.current_target_temperature(progress)
        set_point = target - self.tolerance
        if heating_state:
            set_point = target
        if self._moving_avg_temp < set_point:
            self.log.info(
                ("heating required (g_now=%.2f, g_avg=%.2f, progress=%.2fpct, "
                 "t_now=%.1f, t_avg=%.1f, t_target=%.1f, t_set_point=%.1f, "
                 "tolerance=%.2f)"),
                gravity, self._moving_avg_grav, progress*100, current_temp,
                self._moving_avg_temp, target, set_point, self.tolerance)
            return True
        return False

    def requires_cooling(self, heating_state, cooling_state):
        gravity = self._get_gravity()
        current_temp = self._get_temperature()
        progress = self.calc_progress(self._moving_avg_grav)
        target = self.current_target_temperature(progress)
        set_point = target + self.tolerance
        if cooling_state:
            set_point = target
        if self._moving_avg_temp > set_point:
            self.log.info(
                ("cooling required (g_now=%.2f, g_avg=%.2f, progress=%.2fpct, "
                 "t_now=%.1f, t_avg=%.1f, t_target=%.1f, t_set_point=%.1f, "
                 "tolerance=%.2f)"),
                gravity, self._moving_avg_grav, progress*100, current_temp,
                self._moving_avg_temp, target, set_point, self.tolerance)
            return True
        return False

    def calc_progress(self, gravity):
        """
        Calculates the current progress of fermentation based on the current
        gravity compared to the target.
        """
        if gravity > self.original_gravity:
            gravity = self.original_gravity
        elif gravity < self.final_gravity:
            gravity = self.final_gravity
        return (self.original_gravity - gravity) / float(
            self.original_gravity - self.final_gravity)

    def current_target_temperature(self, progress):
        """
        Calculates what the current target temperature should be based on the
        progress of fermentation.
        """
        return (self.end_set_point - self.start_set_point) * progress + self.start_set_point

class DampenedBeer(LinearBeer):
    """
    This type of beer works almost the same as LinearBeer, except that instead
    of the temperature of the beer being ramped linearly as the gravity goes
    down, the warming is dampened such that most of the ramping occurs late in
    fermentation. All of the options are the same as for LinearBeer, with the
    exception of the new option, `damping_factor`, which should be a float
    between 0 and 1.0, where higher values result in more of the warming
    happening during the last 10-15 percent of
    fermentation. The default damping factor is 0.6, which results in only 1/8th
    of the warming occuring by 40 percent of fermentation, 1/2 by 80 percent,
    and the rest occuring during the final 20 percent of fermentation.
    """

    def __init__(self, name, **kwargs):
        super(DampenedBeer, self).__init__(name, **kwargs)
        self.damping_factor = float(kwargs.pop('damping_factor', 0.6))

    def current_target_temperature(self, progress):
        """
        Calculates the temperature target using a formula similar to this:

            (progress * (1 - damping_factor) / (2 - damping_factor - progress)) * (t_end - t_start) + t_start
        """
        return (progress * (1 - self.damping_factor) / \
            (2 - self.damping_factor - progress)) * \
            (self.end_set_point - self.start_set_point) + self.start_set_point
