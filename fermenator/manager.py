import logging
import threading
import time

class ManagerThread(threading.Thread):
    """
    Create one of these for every beer that needs to be managed.

    Pass in an :class:`Beer` object representing the beer to be
    managed, as well as a :class:`relay` object for each of cooling or heating,
    as desired.
    """

    def __init__(self, beer, polling_frequency=60):
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self.beer.name))
        self.beer = beer
        self.polling_frequency = polling_frequency
        self._enable_active_cooling = False
        self._enable_active_heating = False
        self._enable_active_cooling_relay = None
        self._enable_active_heating_relay = None
        self._stop = False
        threading.Thread.__init__(self)

    def set_active_cooling_relay(self, relay):
        self.log.debug("cooling relay set")
        self._active_cooling_relay = relay

    def set_active_heating_relay(self, relay):
        self.log.debug("heating relay set")
        self._active_heating_relay = relay

    def enable_active_heating(self):
        self.log.info("active heating enabled")
        self._enable_active_heating = True

    def disable_active_heating(self):
        self.log.info("active heating disabled")
        self._enable_active_heating = False

    def enable_active_cooling(self):
        self.log.info("active cooling enabled")
        self._enable_active_cooling = True

    def disable_active_cooling(self):
        self.log.info("active cooling disabled")
        self._enable_active_cooling = False

    def run(self):
        self.log.debug("started")
        while not self._stop:
            self.log.debug("in loop - checking on beer")
            if self.beer.requires_heating():
                if self._active_cooling_relay:
                    self._active_heating_relay.off()
                if self._enable_active_heating:
                    if self._active_heating_relay:
                        self._active_heating_relay.on()
                    else:
                        self.log.warning("heating required but no active heating relay set")
                else:
                    self.log.warning("active heating required but disabled")
            elif self.beer.requires_cooling():
                if self._active_heating_relay:
                    self._active_heating_relay.off()
                if self._enable_active_cooling:
                    if self._active_cooling_relay:
                        self._active_cooling_relay.on()
                    else:
                        self.log.warning("cooling required but no active cooling relay set")
                else:
                    self.log.warning("active cooling required but disabled")
            # TODO: use the time from the beginning of the loop to calculate the next sleep interval
            time.sleep(self.polling_frequency)
        self.log.debug("finished")

    def stop(self):
        self._stop = True
        self.log.debug("called")
