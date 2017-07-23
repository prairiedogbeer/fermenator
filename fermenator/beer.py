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
import logging
import datetime
import collections
from .exception import (
    StaleDataError, ConfigurationError, DataFetchError,
    InvalidTemperatureError, InvalidGravityError)

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
        self._config = kwargs
        if 'data_age_warning_time' in self._config:
            self._config['data_age_warning_time'] = float(
                self._config['data_age_warning_time'])
        else:
            self._config['data_age_warning_time'] = 60 * 30
        try:
            self.gravity_unit = self._config['gravity_unit']
        except KeyError:
            self.gravity_unit = 'P'
        try:
            self.temperature_unit = self._config['temperature_unit']
        except KeyError:
            self.temperature_unit = 'C'

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

    @property
    def data_age_warning_time(self):
        """
        Returns the configured data_age_warning_time
        """
        return self._config['data_age_warning_time']

    @data_age_warning_time.setter
    def data_age_warning_time(self, value):
        """
        Set the data_age_warning_time
        """
        self.log.info("configuring data_age_warning_time at %f", value)
        self._config['data_age_warning_time'] = value

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
            self.read_datasource = kwargs['read_datasource']
        except KeyError:
            raise ConfigurationError("read_datasource is required in kwargs")
        if 'identifier' not in self._config:
            raise ConfigurationError("no identifier specified in beer config")
        try:
            self._config['set_point'] = float(self._config['set_point'])
        except KeyError:
            raise ConfigurationError("no set_point in kwargs")
        try:
            self._config['tolerance'] = float(self._config['tolerance'])
        except KeyError:
            self._config['tolerance'] = 0.5
        try:
            self.moving_average_size = int(kwargs['moving_average_size'])
        except KeyError:
            self.moving_average_size = 10
        try:
            self.max_temp_value = float(kwargs['max_temp_value'])
        except KeyError:
            self.max_temp_value = 35.0
        try:
            self.min_temp_value = float(kwargs['min_temp_value'])
        except KeyError:
            self.min_temp_value = -5.0
        self._temp_readings = collections.deque(
            [None]*self.moving_average_size, self.moving_average_size)
        self._moving_avg_temp = None

    @property
    def set_point(self):
        "Returns the configured set point for this beer"
        return self._config['set_point']

    @set_point.setter
    def set_point(self, value):
        "Configure the set point for this beer"
        self.log.info("configuring set point at %f", float(value))
        self._config['set_point'] = float(value)

    @property
    def tolerance(self):
        "Returns the configured temperature tolerance for this beer"
        return self._config['tolerance']

    @tolerance.setter
    def tolerance(self, value):
        "Set the temperature tolerance for this beer"
        self.log.info("configuring set point tolerance at %f", float(value))
        self._config['tolerance'] = value

    def _get_temperature(self, retries=3):
        "Get the current temperature of the beer, log error if old"
        for _ in range(0, 3):
            try:
                data = self.read_datasource.get_temperature(
                    self._config['identifier'])
                if (data['temperature'] > self.max_temp_value) or \
                    (data['temperature'] < self.min_temp_value):
                    raise InvalidTemperatureError(
                        "temperature {} doesn't appear to be valid".format(
                            data['temperature']))
                self.check_timestamp(data['timestamp'])
                self._add_temp(data['temperature'])
                return data['temperature']
            except BaseException as err:
                self.log.warning(
                    "exception reading/parsing temp from datastore: %s", err)
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
            set_point = self.set_point + self.tolerance
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
            set_point = self.set_point - self.tolerance
        if self._moving_avg_temp > set_point:
            self.log.info(
                "cooling required (t_now=%.1f, t_avg=%.1f t_target=%.1f "
                "t_set_point=%.1f, tolerance=%.2f)",
                temp, self._moving_avg_temp, self.set_point, set_point,
                self.tolerance)
            return True

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
            self.read_datasource = kwargs['read_datasource']
        except KeyError:
            raise ConfigurationError("read_datasource is required in kwargs")
        try:
            self.identifier = self._config['identifier']
        except KeyError:
            raise ConfigurationError("No identifier provided")
        try:
            self.original_gravity = float(self._config['original_gravity'])
        except KeyError:
            raise ConfigurationError("original_gravity must be specified")
        try:
            self.final_gravity = float(self._config['final_gravity'])
        except KeyError:
            raise ConfigurationError("final_gravity must be specified")
        try:
            self.start_set_point = float(self._config['start_set_point'])
        except KeyError:
            raise ConfigurationError("start_set_point must be specified")
        try:
            self.end_set_point = float(self._config['end_set_point'])
        except KeyError:
            raise ConfigurationError("end_set_point must be specified")
        try:
            self.tolerance = float(self._config['tolerance'])
        except KeyError:
            self.tolerance = 0.5
        try:
            self.max_temp_value = float(kwargs['max_temp_value'])
        except KeyError:
            self.max_temp_value = 35.0
        try:
            self.min_temp_value = float(kwargs['min_temp_value'])
        except KeyError:
            self.min_temp_value = -5.0
        try:
            self.moving_average_size = int(kwargs['moving_average_size'])
        except KeyError:
            self.moving_average_size = 10
        self._temp_readings = collections.deque(
            [None]*self.moving_average_size, self.moving_average_size)
        self._moving_avg_temp = None
        self._grav_readings = collections.deque(
            [None]*self.moving_average_size, self.moving_average_size)
        self._moving_avg_grav = None

    def _get_temperature(self, retries=3):
        """
        Get temeperature data from the read_datasource
        """
        for _ in range(0, 3):
            try:
                data = self.read_datasource.get_temperature(
                    self._config['identifier'])
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
            except BaseException as err:
                self.log.warning(
                    "exception reading/parsing temp from datastore: %s", err)
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
        for _ in range(0, 3):
            try:
                data = self.read_datasource.get_gravity(self._config['identifier'])
                self.check_timestamp(data['timestamp'])
                self._add_grav(data['gravity'])
                return data['gravity']
            except BaseException as err:
                self.log.warning(
                    "exception reading/parsing gravity from datastore: %s", err)
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
        try:
            gravity = self._get_gravity()
            current_temp = self._get_temperature()
        except StaleDataError as err:
            self.log.error(str(err), exc_info=0)
            return False
        progress = self.calc_progress(self._moving_avg_grav)
        target = self.current_target_temperature(progress)
        set_point = target - self.tolerance
        if heating_state:
            set_point = target + self.tolerance
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
        try:
            gravity = self._get_gravity()
            current_temp = self._get_temperature()
        except StaleDataError as err:
            self.log.error(str(err), exc_info=0)
            return False
        progress = self.calc_progress(self._moving_avg_grav)
        target = self.current_target_temperature(progress)
        set_point = target + self.tolerance
        if cooling_state:
            set_point = target - self.tolerance
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
