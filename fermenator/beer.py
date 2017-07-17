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

class StaleDataError(RuntimeError):
    "Raise this error when data appears to be out of date"
    pass

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

    def requires_heating(self):
        "Implement this method in a subclass using the algorithm of your choice"
        pass

    def requires_cooling(self):
        "Implement this method in a subclass using the algorithm of your choice"
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

    @property
    def datasource(self):
        """
        Returns the configured datasource for this beer
        """
        return self._config['datasource']

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
    approach like you'd find on an STC-1000.
    """

    def __init__(self, name, **kwargs):
        """
        kwargs can include the following:

        - datasource (object)
        - identifier (the identifier used at the datasource for this beer)
        - set_point (float)
        - tolerance (optional, in the same units as the beer)
        - data_age_warning_time (optional, in seconds)
        - gravity_unit (optional, defaults to 'P', plato)
        - temperature_unit (optional, defaults to 'C', celcius)
        """
        super(SetPointBeer, self).__init__(name, **kwargs)
        if 'datasource' not in self._config:
            raise RuntimeError("datasource is required in kwargs")
        if 'identifier' not in self._config:
            raise RuntimeError("no identifier specified in beer config")
        try:
            self._config['set_point'] = float(self._config['set_point'])
        except KeyError:
            raise RuntimeError("no set_point in kwargs")
        if 'tolerance' in self._config:
            self._config['tolerance'] = float(self._config['tolerance'])
        else:
            self._config['tolerance'] = 0.5

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

    def _get_temperature(self):
        "Get the current temperature of the beer, log error if old"
        data = self.datasource.get_temperature(self._config['identifier'])
        self.check_timestamp(data['timestamp'])
        return data['temperature']

    def requires_heating(self):
        """
        Returns True if the beer requires heating based on the set point,
        current temperature, and configured tolerance, False otherwise. If
        data is older than the configured :attr:`data_age_warning_time`,
        returns False, ensuring that the beer is not accidentally heated.
        """
        if self.set_point is None:
            return False
        try:
            temp = self._get_temperature()
        except StaleDataError as err:
            self.log.error(str(err), exc_info=0)
            return False
        if self.set_point > (temp + self.tolerance):
            self.log.info(
                "heating required (temp=%.1f, set_point=%.1f, tolerance=%.2f)",
                temp, self.set_point, self.tolerance)
            return True

    def requires_cooling(self):
        """
        Returns True if the beer is warmer than the set point by more than
        the configured tolerance, False otherwise.
        """
        if self.set_point is None:
            return False
        try:
            temp = self._get_temperature()
        except RuntimeError as err:
            self.log.error(str(err), exc_info=0)
            return False
        if (self.set_point + self.tolerance) < temp:
            self.log.info(
                "cooling required (temp=%.1f, set_point=%.1f, tolerance=%.2f)",
                temp, self.set_point, self.tolerance)
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

        - original_gravity (in Plato or SG depending on gravity_unit)
        - final_gravity (in Plato or SG)
        - start_set_point (where to start the beer)
        - end_set_point (where to finish the beer)
        - tolerance (optional, defaults to 0.5 degrees)
        """
        super(LinearBeer, self).__init__(name, **kwargs)
        try:
            self.original_gravity = float(self._config['original_gravity'])
        except KeyError:
            raise RuntimeError("original_gravity must be specified")
        try:
            self.final_gravity = float(self._config['final_gravity'])
        except KeyError:
            raise RuntimeError("final_gravity must be specified")
        try:
            self.start_set_point = float(self._config['start_set_point'])
        except KeyError:
            raise RuntimeError("start_set_point must be specified")
        try:
            self.end_set_point = float(self._config['end_set_point'])
        except KeyError:
            raise RuntimeError("end_set_point must be specified")
        try:
            self.tolerance = float(self._config['tolerance'])
        except KeyError:
            self.tolerance = 0.5

    def _get_temperature(self):
        data = self.datasource.get_temperature(self._config['identifier'])
        self.check_timestamp(data['timestamp'])
        return data['temperature']

    def _get_gravity(self):
        data = self.datasource.get_gravity(self._config['identifier'])
        self.check_timestamp(data['timestamp'])
        return data['gravity']

    def requires_heating(self):
        try:
            gravity = self._get_gravity()
            current_temp = self._get_temperature()
        except StaleDataError as err:
            self.log.error(str(err), exc_info=0)
            return False
        progress = self.calc_progress(gravity)
        target = self.current_target_temperature(progress)
        if (target - current_temp) > self.tolerance:
            self.log.info(
                ("heating required (gravity=%.2f, progress=%.2fpct, "
                 "temp=%.1f, target_temp=%.1f, tolerance=%.2f)"),
                gravity, progress*100, current_temp, target, self.tolerance
                )
            return True
        return False

    def requires_cooling(self):
        try:
            gravity = self._get_gravity()
            current_temp = self._get_temperature()
        except StaleDataError as err:
            self.log.error(str(err), exc_info=0)
            return False
        progress = self.calc_progress(gravity)
        target = self.current_target_temperature(progress)
        if (current_temp - target) > self.tolerance:
            self.log.info(
                ("cooling required (gravity=%.2f, progress=%.2fpct, "
                 "temp=%.1f, target_temp=%.1f, tolerance=%.2f)"),
                gravity, progress*100, current_temp, target, self.tolerance
                )
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
