"""
Profiles are used to control how beer is heated or cooled. For example,
profiles can be used to crash cool a beer aggressively, or to gently nudge
the beer in one direction or another.
"""
import time
import logging
import random
import datetime
import collections
from .exception import (
    StaleDataError, ConfigurationError, DataFetchError,
    InvalidTemperatureError, DataSourceError)

HEATING_STATE = 'HEATING'
COOLING_STATE = 'COOLING'
PASSIVE_STATE = 'PASSIVE'
ALL_STATES = [HEATING_STATE, COOLING_STATE, PASSIVE_STATE]

class Profile():
    """
    Base, abstract profile class. Implements the main APIs but no logic.
    """
    def __init__(self, fermenter, **kwargs):
        """
        Inititalize the class
        """
        self.fermenter = fermenter
        self._args = kwargs
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self.fermenter))

    def make_recommendation(self):
        """
        Return one of three recommendations based on sensor data:
         - 'heat'
         - 'cool'
         - 'passive' (do nothing)
        """
        pass

class TestProfile(Profile):
    """
    Used for testing purposes. Randomly makes recommendations
    """
    def make_recommendation(self):
        "Return a random state choice"
        return random.choice(ALL_STATES)

class SetPoint(Profile):
    """
    This :class:`Profile` implements a "dumb" set-point
    approach like you'd find on an STC-1000, with basic hysteresis.

    Pass in the following arguments:

    - temp_sensor (required) a sensor object
    - set_point (float, required)
    - tolerance (optional, defaults to 0.5)
    """
    def __init__(self, fermenter, **kwargs):
        """
        Initialize the class
        """
        super(SetPoint, self).__init__(fermenter, **kwargs)
        try:
            self.temp_sensor = kwargs.pop('temp_sensor')
        except KeyError:
            raise ConfigurationError("temp_sensor argument required")
        try:
            self.set_point = float(kwargs.pop('set_point'))
        except KeyError:
            raise ConfigurationError("set_point argument required")
        self.tolerance = float(kwargs.pop('tolerance', 0.5))
        self.state = PASSIVE_STATE

    def get_recommendation(self):
        """
        Returns a recommendation based on the temperature readings
        """
        rval = PASSIVE_STATE
        temp = self.temp_sensor.fetch()
        target = self.get_target_set_point()
        if self.state == PASSIVE_STATE and \
            abs(temp - self.set_point) < self.tolerance:
            rval = PASSIVE_STATE
        if self.state == COOLING_STATE and \
            temp > target:
            rval = COOLING_STATE
        if self.state == HEATING_STATE and \
            temp < target:
            rval = HEATING_STATE
        if rval != self.state:
            self.state_change_hook(self.state, rval)
        else:
            self.stable_state_hook(rval)
        self.state = rval
        return rval

    def state_change_hook(self, old_state, new_state):
        """
        Run this code when the state changes. Useful when extending the class.
        By default, just logs the state change info.
        """
        self.log.info(
            "new_state=%s old_state=%s moving_avg_temp=%.1f "
            "set_point=%.1f tolerance=%.2f",
            new_state, old_state, self.temp_sensor.fetch_last(),
            self.set_point, self.tolerance")

    def stable_state_hook(self, state):
        """
        Run this code whenever the state recommendation is unchanged. Useful
        when extending the class. Logs a debug statement with state info.
        """
        self.log.debug(
            "state=%s moving_avg_temp=%.1f "
            "set_point=%.1f tolerance=%.2f",
            state, self.temp_sensor.fetch_last(),
            self.set_point, self.tolerance")

    def get_target_set_point(self):
        """
        Gets the current set point based on state and tolerance. For example,
        if the user set point is 20, with a tolerance of 1, and we are
        currently cooling the beer, then the set point will actually be 19
        degrees to allow cooling to overshoot a little.
        """
        tolerance = self.tolerance
        if self.state == COOLING_STATE:
            tolerance *= -1.0
        return self.set_point + tolerance
