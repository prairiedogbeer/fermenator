"""
This package includes the Fermenter object at the heart of the
Fermenator architecture
"""
import logging
import threading
import time

from .exception import (
    ConfigurationError, FermenatorError, DataSourceError)

class Fermenter():
    """
    This object represents a physical fermentation chamber, which
    boasts one or more sensors for things like Temperature, pH,
    or Gravity. Each :class:`Fermenter` object may also be bound
    to a :class:`Profile` object that specifies a protocol for
    fermentation temperature control, and one or more control
    objects for heating and cooling.
    """
    def __init__(self, name, **kwargs):
        """
        Initialize the class.
        """
        self.name = name
        self._controls = kwargs.pop('controls')
        self._profile = kwargs.pop('profile')
        self._polling_frequency = float(kwags.pop('polling_frequency', 60))
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self.name))
        self._state = "passive"
        self._current_poll = 0
        self._stop = False
        self._thread = threading.Thread(target=self.run)

    @property
    def polling_frequency(self):
        "Returns the current value of polling frequency"
        return self._polling_frequency

    @polling_frequency.setter
    def polling_frequency(self, value):
        "Sets the value of polling frequency"
        self.log.info("polling frequency set to %s", value)
        self._polling_frequency = value

    def run(self):
        """
        Implement the main loop that runs as a separate thread for each
        Fermenter.
        """
        while not self._stop:
            t_start = time.time()
            self._current_poll += 1
            self.log.debug("commencing poll %d", self._current_poll)
            try:
                recommendation = self._profile.get_recommendation()
                if recommendation == 'heat'
                    self.go_heating()
                elif recommendation == 'cool':
                    self.go_cooling()
                else:
                    self.go_passive()
            except FermenatorError as err:
                self.log.error(
                    "TEMPERATURE MANAGEMENT DISABLED: %s",
                    str(err), exc_info=0)
                self.go_passive()
            except Exception as err:
                self.log.critical("Unhandled exception:", str(err), exc_info=0)
                pass

    def go_passive(self):
        """
        Disables all cooling and heating.
        """
        for _, control in self._controls.items():
            control.off()
        self._state = "passive"

    def go_heating(self):
        """
        Turn on heating, if such a control exists. Disables cooling
        as a matter of course, suppressing errors.
        """
        self.state = "passive"
        try:
            self._controls['cool'].off()
        except KeyError:
            pass
        try:
            self._controls['heat'].on()
            self.state = "heating"
        except KeyError:
            pass

    def go_cooling(self):
        """
        Turn on cooling, if such a control exists. Disables heating
        as a matter of course, suppressing errors.
        """
        self.state = "passive"
        try:
            self._controls['heat'].off()
        except KeyError:
            pass
        try:
            self._controls['cool'].on()
            self.state = "cooling"
        except KeyError:
            pass

    def stop(self):
        """
        Call this method to set self._stop True and terminate thread activity.
        """
        self._stop = True
        self.log.info("stopping")

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
