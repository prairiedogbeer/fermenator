import logging
import threading
import time

class ManagerThread(threading.Thread):
    """
    Create one of these for every beer that needs to be managed.

    Pass in a :class:`Beer` object representing the beer to be
    managed, as well as a :class:`Relay` object for each of cooling or heating,
    as desired.
    """

    def __init__(self, beer, **kwargs):
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                beer.name))
        self.beer = beer
        self.log.debug(kwargs)
        self.active_cooling = active_cooling
        self.active_heating = active_heating
        if active_cooling_relay:
            self.active_cooling_relay = active_cooling_relay
        if active_heating_relay:
            self.active_heating_relay = active_heating_relay
        self.polling_frequency = polling_frequency
        self._stop = False
        threading.Thread.__init__(self)

    def __destroy__(self):
        self._stop = True

    @property
    def polling_frequency(self):
        return self._polling_frequency

    @polling_frequency.setter
    def polling_frequency(self, value):
        self.log.info("polling frequency set to {}".format(value))
        self._polling_frequency = value

    @property
    def active_cooling_relay(self):
        return self._active_cooling_relay

    @active_cooling_relay.setter
    def active_cooling_relay(self, relay):
        self.log.debug("cooling relay set to {}".format(relay.name))
        self._active_cooling_relay = relay

    @property
    def active_heating_relay(self):
        return self._active_heating_relay

    @active_heating_relay.setter
    def active_heating_relay(self, relay):
        self.log.debug("heating relay set to {}".format(relay.name))
        self._active_heating_relay = relay

    @property
    def active_heating(self):
        return self._enable_active_heating

    @active_heating.setter
    def active_heating(self, value):
        if value:
            self.log.info("active heating enabled")
            self._enable_active_heating = True
        else:
            self.log.info("active heating disabled")
            self._enable_active_heating = False

    @property
    def active_cooling(self):
        return self._enable_active_cooling

    @active_cooling.setter
    def active_cooling(self, value):
        if value:
            self.log.info("active cooling enabled")
            self._enable_active_cooling = True
        else:
            self.log.info("active cooling disabled")
            self._enable_active_cooling = False

    def run(self):
        self.log.debug("started")
        while not self._stop:
            t_start = time.time()
            self.log.debug("checking on beer")
            if self.beer.requires_heating():
                self._do_heating()
            elif self.beer.requires_cooling():
                self._do_cooling()
            while not self._stop and ((time.time() - t_start) < self.polling_frequency):
                time.sleep(1)
        self._shut_off_relays()
        self.log.debug("finished")

    def stop(self):
        self._stop = True
        self.log.info("stopping")

    def _do_heating(self):
        if self.active_cooling_relay:
            self.active_cooling_relay.off()
        if self._enable_active_heating:
            if self.active_heating_relay:
                self.active_heating_relay.on()
            else:
                self.log.warning("heating required but no active heating relay set")
        else:
            self.log.warning("active heating required but disabled")

    def _do_cooling(self):
        if self.active_heating_relay:
            self.active_heating_relay.off()
        if self._enable_active_cooling:
            if self.active_cooling_relay:
                self.active_cooling_relay.on()
            else:
                self.log.warning("cooling required but no active cooling relay set")
        else:
            self.log.warning("active cooling required but disabled")

    def _shut_off_relays(self):
        if self.active_cooling_relay:
            self.active_cooling_relay.off()
        if self.active_heating_relay:
            self.active_heating_relay.off()
