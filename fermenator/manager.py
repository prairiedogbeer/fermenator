"""
This package includes the :class:`ManagerThread` object that manages each beer.
"""
import logging
import threading
import time

import fermenator.statelogger
from .exception import ConfigurationError, FermenatorError

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
        - state_loggers: dictionary of state loggers (optional)
        """
        self.name = name
        if 'beer' not in kwargs:
            raise ConfigurationError("'beer' must be specified in kwargs")
        self.beer = kwargs['beer']
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self.beer.name))
        try:
            self._active_cooling = kwargs['active_cooling']
        except KeyError:
            self._active_cooling = False
        try:
            self._active_heating = kwargs['active_heating']
        except KeyError:
            self._active_heating = False
        try:
            self._active_cooling_relay = kwargs['active_cooling_relay']
        except KeyError:
            self._active_cooling_relay = None
        try:
            self._active_heating_relay = kwargs['active_heating_relay']
        except KeyError:
            self._active_heating_relay = None
        try:
            self._polling_frequency = float(kwargs['polling_frequency'])
        except KeyError:
            self._polling_frequency = 60
        try:
            self.state_loggers = kwargs['state_loggers']
        except KeyError:
            self.log.info("no state loggers defined")
            self.state_loggers = dict()
        self._stop = False
        self._thread = threading.Thread(target=self.run)

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

    def isAlive(self):
        """
        Pass-through to thread isAlive() method.
        """
        return self._thread.isAlive()

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
        while not self._stop:
            t_start = time.time()
            self.log.debug("checking on beer: %s", self.beer.name)
            try:
                if self.beer.requires_heating(self.is_heating(), self.is_cooling()):
                    self._stop_cooling()
                    self._start_heating()
                elif self.beer.requires_cooling(self.is_heating(), self.is_cooling()):
                    self._stop_heating()
                    self._start_cooling()
                else:
                    self.log.info("beer %s is at set point", self.beer.name)
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
            return self.active_heating_relay.is_on()
        except AttributeError:
            return False

    def is_cooling(self):
        "Returns True if the managed beer is currently being cooled"
        try:
            return self.active_cooling_relay.is_on()
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
                self.active_heating_relay.on()
            except AttributeError:
                self.log.warning(
                    "heating required but no active heating relay set")
        else:
            self.log.warning("active heating required but disabled")

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
                self.active_cooling_relay.on()
            except AttributeError:
                self.log.warning(
                    "cooling required but no active cooling relay set")
        else:
            self.log.warning("active cooling required but disabled")

    def _stop_cooling(self):
        """
        Call this method whenever cooling is started or when heat is no longer
        required.
        """
        try:
            self.active_cooling_relay.off()
        except AttributeError:
            pass

    def _log_state(self):
        for logger in self.state_loggers:
            self.state_loggers[logger].log_heartbeat(self.beer)
        if self.is_heating():
            for logger in self.state_loggers:
                self.state_loggers[logger].log_heating_on(self.beer)
        else:
            for logger in self.state_loggers:
                self.state_loggers[logger].log_heating_off(self.beer)
        if self.is_cooling():
            for logger in self.state_loggers:
                self.state_loggers[logger].log_cooling_on(self.beer)
        else:
            for logger in self.state_loggers:
                self.state_loggers[logger].log_cooling_off(self.beer)
