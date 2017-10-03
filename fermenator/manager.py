"""
This package includes the :class:`ManagerThread` object that manages each beer.
"""
import logging
import threading
import time

from .exception import (
    ConfigurationError, FermenatorError, DataSourceError)

class ManagerThread():
    """
    Create one of these for every beer that needs to be managed.

    Pass in a :class:`Beer` object representing the beer to be
    managed, as well as a :class:`Relay` object for each of cooling or heating,
    as desired.
    """

    def __init__(self, name, **kwargs):
        """
        Pass a name plus one or more of the following arguments:

        - beer: beer-type object to manage (required)
        - active_cooling: boolean - whether or not to enable cooling
        - active_heating: boolean - whether or not to enable heating
        - active_cooling_relay: relay object used for cooling the beer
        - active_heating_relay: relay object used for heating the beer
        - polling_frequency: how often to check the beer (float)
        - write_datasources: an optional list of datasources to write
          state information to
        - state_path_prefix: a prefix where to write state information in
          write_datasources [default: fermenator.state]

        """
        self.name = name
        if 'beer' not in kwargs:
            raise ConfigurationError("'beer' must be specified in kwargs")
        self.beer = kwargs['beer']
        self.log = logging.getLogger(
            "{}.{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self.name,
                self.beer.name))
        self._active_cooling = kwargs.pop('active_cooling', False)
        self._active_heating = kwargs.pop('active_heating', False)
        self._active_cooling_relay = kwargs.pop('active_cooling_relay', None)
        self._active_heating_relay = kwargs.pop('active_heating_relay', None)
        self._polling_frequency = float(kwargs.pop('polling_frequency', 60))
        self._target_efficacy = float(
            kwargs.pop('target_efficacy', 1 / 60.0))
        try:
            self.write_datasources = kwargs['write_datasources']
        except KeyError:
            self.log.info("no write datasources defined, state logging disabled")
            self.write_datasources = dict()
        self.state_path_prefix = tuple(
            kwargs.pop('state_path_prefix', "fermenator.state").split('.'))
        self._npolls_wait_duty_change = 5
        self._heat_duty_cycle_increment = 0.05
        self._cool_duty_cycle_increment = 0.01
        self._current_poll = 0
        self._stop = False
        self._thread = threading.Thread(target=self.run)
        self._heat_duty_cycle = None
        self._cool_duty_cycle = None
        self._last_heat_duty_change_poll = None
        self._last_cool_duty_change_poll = None
        self._last_heat_on_time = None
        self._last_cool_on_time = None
        self._last_heat_on_temp = None
        self._last_cool_on_temp = None

    def __del__(self):
        """
        Called automatically during garbage collection. When called, sets
        self._stop to True, to try to ensure that any thread action is
        discontinued.
        """
        self.log.debug("destructing")
        self._stop = True

    def start(self):
        """
        Starts the :meth:`run` method inside a thread.
        """
        self._thread.start()

    def join(self, timeout=None):
        """
        Pass-through to the thread join method.
        """
        self._thread.join(timeout)

    def is_alive(self):
        """
        Pass-through to thread is_alive() method.
        """
        return self._thread.is_alive()

    @property
    def polling_frequency(self):
        "Returns the current value of polling frequency"
        return self._polling_frequency

    @polling_frequency.setter
    def polling_frequency(self, value):
        "Sets the value of polling frequency"
        self.log.info("polling frequency set to %s", value)
        self._polling_frequency = value

    @property
    def active_cooling_relay(self):
        "Returns the currently configured active_cooling_relay"
        return self._active_cooling_relay

    @active_cooling_relay.setter
    def active_cooling_relay(self, relay):
        "Sets the active_cooling_relay, provide a relay-type object"
        if relay:
            self.log.debug("cooling relay set to %s", relay.name)
        else:
            self.log.debug("cooling relay disabled")
        self._active_cooling_relay = relay

    @property
    def active_heating_relay(self):
        "Returns the currentlyconfigured active_heating_relay"
        return self._active_heating_relay

    @active_heating_relay.setter
    def active_heating_relay(self, relay):
        "Sets the active_heating_relay, provide a relay-type object"
        if relay:
            self.log.debug("heating relay set to %s", relay.name)
        else:
            self.log.debug("heating relay disabled")
        self._active_heating_relay = relay

    @property
    def active_heating(self):
        "Returns the boolean value of active heating"
        return self._active_heating

    @active_heating.setter
    def active_heating(self, value):
        "Sets the boolean value of active heating"
        if value:
            self.log.info("active heating enabled")
            self._active_heating = True
        else:
            self.log.info("active heating disabled")
            self._active_heating = False

    @property
    def active_cooling(self):
        "Returns the current value of active cooling"
        return self._active_cooling

    @active_cooling.setter
    def active_cooling(self, value):
        "Sets the current value of active cooling (boolean)"
        if value:
            self.log.info("active cooling enabled")
            self._active_cooling = True
        else:
            self.log.info("active cooling disabled")
            self._active_cooling = False

    def run(self):
        """
        Checks on the state of the monitored beer, and enables or disables
        heating accordingly. Runs in an infinite loop that can only be
        interrupted by self._stop being set True (which is checked once per
        quarter second). Ensurses that relays are disabled on shutdown.
        """
        self.log.debug("started")
        self._current_poll += 1
        while not self._stop:
            t_start = time.time()
            try:
                if self.beer.requires_heating(self.is_heating(), self.is_cooling()):
                    self._stop_cooling()
                    self._start_heating()
                elif self.beer.requires_cooling(self.is_heating(), self.is_cooling()):
                    self._stop_heating()
                    self._start_cooling()
                else:
                    self.log.info("at set point")
                    self._stop_heating()
                    self._stop_cooling()
            except FermenatorError as err:
                self.log.error(
                    "TEMPERATURE MANAGEMENT DISABLED: %s",
                    str(err), exc_info=0)
                self._stop_heating()
                self._stop_cooling()
            self._log_state()
            while not self._stop and ((time.time() - t_start) < self.polling_frequency):
                time.sleep(0.25)
        self._stop_heating()
        self._stop_cooling()
        self._log_state()
        self.log.debug("finished")

    def stop(self):
        """
        Call this method to set self._stop True and terminate thread activity.
        """
        self._stop = True
        self.log.info("stopping")

    def is_heating(self):
        "Returns True if the managed beer is currently being heated"
        try:
            return self.active_heating_relay.is_running()
        except AttributeError:
            return False

    def is_cooling(self):
        "Returns True if the managed beer is currently being cooled"
        try:
            return self.active_cooling_relay.is_running()
        except AttributeError:
            return False

    def _start_heating(self):
        """
        This method is called whenever the beer thinks it needs heating, and
        handles the logic of determining if a relay is present and if config
        allows for active heating.
        """
        if self.active_heating:
            try:
                if not self.active_heating_relay.is_running():
                    self._last_heat_on_time = time.time()
                    self._last_heat_on_temp = self.beer.avg_temp()
                    self.active_heating_relay.on()
                elif (self._current_poll - self._last_heat_duty_change_poll) \
                    > self._npolls_wait_duty_change:
                    delta_t = self.beer.avg_temp() - self._last_heat_on_temp
                    efficacy_now = delta_t / (self._current_poll - \
                        self._last_heat_duty_change_poll)
                    if efficacy_now < self._target_efficacy:
                        self._increase_heating_efficacy()
                    elif efficacy_now > self._target_efficacy:
                        self._decrease_heating_efficacy()
            except AttributeError:
                self.log.warning(
                    "heating required but no active heating relay set")
        else:
            self.log.warning("active heating required but disabled")

    def _decrease_heating_efficacy(self):
        "Decreases the duty cycle of heating"
        self._heat_duty_cycle -= self._heat_duty_cycle_increment
        self._active_heating_relay.alter_duty_cycle(
            self._heat_duty_cycle)
        self.log.info(
            "heating duty cycle decreased to %0.2f",
            self._heat_duty_cycle)
        self._last_heat_duty_change_poll = self._current_poll

    def _increase_heating_efficacy(self):
        "Increases the duty cycle of heating"
        if self._heat_duty_cycle >= 100:
            self.log.warning(
                "heating is insufficient for current ambient")
        else:
            self._heat_duty_cycle += self._heat_duty_cycle_increment
            self._active_heating_relay.alter_duty_cycle(
                self._heat_duty_cycle)
            self.log.info(
                "heating duty cycle increased to %0.2f",
                self._heat_duty_cycle)
            self._last_heat_duty_change_poll = \
                self._current_poll

    def _stop_heating(self):
        """
        Call this method whenever cooling is started or when heat is no longer
        required.
        """
        try:
            self.active_heating_relay.off()
        except AttributeError:
            pass

    def _start_cooling(self):
        """
        This method is called whenever the beer thinks it needs cooling, and
        handles the logic of determining if a relay is present and if config
        allows for active cooling.
        """
        if self.active_cooling:
            try:
                if not self.active_cooling_relay.is_running():
                    self._last_cool_on_time = time.time()
                    self._last_cool_on_temp = self.beer.avg_temp()
                    self.active_cooling_relay.on()
                elif (self._current_poll - self._last_cool_duty_change_poll) \
                    > self._npolls_wait_duty_change:
                    delta_t = self.beer.avg_temp() - self._last_cool_on_temp
                    efficacy_now = delta_t / (self._current_poll - \
                        self._last_cool_duty_change_poll)
                    if efficacy_now < (-1 * self._target_efficacy):
                        self._decrease_cooling_efficacy()
                    elif efficacy_now > (-1 * self._target_efficacy):
                        self._increase_cooling_efficacy()
            except AttributeError:
                self.log.warning(
                    "cooling required but no active cooling relay set")
        else:
            self.log.warning("active cooling required but disabled")

    def _decrease_cooling_efficacy(self):
        "Decreases the duty cycle of cooling"
        self._cool_duty_cycle -= self._cool_duty_cycle_increment
        self._active_cooling_relay.alter_duty_cycle(
            self._cool_duty_cycle)
        self.log.info(
            "cooling duty cycle decreased to %0.2f",
            self._cool_duty_cycle)
        self._last_cool_duty_change_poll = self._current_poll

    def _increase_cooling_efficacy(self):
        "Increases the duty cycle of cooling"
        if self._cool_duty_cycle >= 100:
            self.log.warning(
                "cooling is insufficient for current ambient")
        else:
            self._cool_duty_cycle += self._cool_duty_cycle_increment
            self._active_cooling_relay.alter_duty_cycle(
                self._cool_duty_cycle)
            self.log.info(
                "cooling duty cycle increased to %0.2f",
                self._cool_duty_cycle)
            self._last_cool_duty_change_poll = \
                self._current_poll

    def _stop_cooling(self):
        """
        Call this method whenever cooling is started or when cool is no longer
        required.
        """
        try:
            self.active_cooling_relay.off()
        except AttributeError:
            pass

    def _log_state(self):
        try:
            now = time.time()
            for logger in self.write_datasources:
                logger.set(
                    self.state_path_prefix + (self.name, "heartbeat"), now)
                if self.is_heating():
                    logger.set(
                        self.state_path_prefix + (self.beer.name, "heating"), 1)
                else:
                    logger.set(
                        self.state_path_prefix + (self.beer.name, "heating"), 0)
                if self.is_cooling():
                    logger.set(
                        self.state_path_prefix + (self.beer.name, "cooling"), 1)
                else:
                    logger.set(
                        self.state_path_prefix + (self.beer.name, "cooling"), 0)
        except DataSourceError as err:
            self.log.error(
                "Error writing state information to datastore: %s", err)
