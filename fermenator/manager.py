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
                beer.name))
        self.beer = beer
        self.polling_frequency = polling_frequency
        self._enable_active_cooling = False
        self._enable_active_heating = False
        self._active_cooling_relay = None
        self._active_heating_relay = None
        self._stop = False
        threading.Thread.__init__(self)

    @property
    def active_cooling_relay(self):
        return self._active_cooling_relay

    @active_cooling_relay.setter
    def active_cooling_relay(self, relay):
        self.log.debug("cooling relay set")
        self._active_cooling_relay = relay

    @property
    def active_heating_relay(self):
        return self._active_heating_relay

    @active_heating_relay.setter
    def active_heating_relay(self, relay):
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

    def _shut_off_relays(self):
        if self.active_cooling_relay:
            self.active_cooling_relay.off()
        if self.active_heating_relay:
            self.active_heating_relay.off()

    def run(self):
        self.log.debug("started")
        while not self._stop:
            t_start = time.time()
            self.log.debug("in loop - checking on beer")
            if self.beer.requires_heating():
                if self.active_cooling_relay:
                    self.active_cooling_relay.off()
                if self._enable_active_heating:
                    if self.active_heating_relay:
                        self.active_heating_relay.on()
                    else:
                        self.log.warning("heating required but no active heating relay set")
                else:
                    self.log.warning("active heating required but disabled")
            elif self.beer.requires_cooling():
                if self.active_heating_relay:
                    self.active_heating_relay.off()
                if self._enable_active_cooling:
                    if self.active_cooling_relay:
                        self.active_cooling_relay.on()
                    else:
                        self.log.warning("cooling required but no active cooling relay set")
                else:
                    self.log.warning("active cooling required but disabled")
            while not self._stop and ((time.time() - t_start) < self.polling_frequency):
                time.sleep(1)
        self._shut_off_relays()
        self.log.debug("finished")

    def stop(self):
        self._stop = True
        self.log.debug("stopping")
