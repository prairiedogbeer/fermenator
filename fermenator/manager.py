import logging
import threading
import time

class ManagerThread():
    """
    Create one of these for every beer that needs to be managed.

    Pass in a :class:`Beer` object representing the beer to be
    managed, as well as a :class:`Relay` object for each of cooling or heating,
    as desired.
    """
    # TODO: Python documentation says that a subclassed Thread object should
    # only implement __init__ and run, nothing else. This object should wrap
    # a thread object and pass in a callable.

    def __init__(self, name, **kwargs):
        if not 'beer' in kwargs:
            raise RuntimeError("'beer' must be specified in kwargs")
        self.beer = kwargs['beer']
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self.beer.name))
        if 'active_cooling' in kwargs:
            self.active_cooling = kwargs['active_cooling']
        else:
            self.active_cooling = False
        if 'active_heating' in kwargs:
            self.active_heating = kwargs['active_heating']
        else:
            self.active_heating = False
        if 'active_cooling_relay' in kwargs:
            self.active_cooling_relay = kwargs['active_cooling_relay']
        else:
            self.active_cooling_relay = None
        if 'active_heating_relay' in kwargs:
            self.active_heating_relay = kwargs['active_heating_relay']
        else:
            self.active_heating_relay = None
        if 'polling_frequency' in kwargs:
            self.polling_frequency = float(kwargs['polling_frequency'])
        else:
            self.polling_frequency = 60
        self._stop = False
        self._thread = threading.Thread(target=self.run)

    def __destroy__(self):
        self.log.debug("__destroy__ called")
        self._stop = True

    def start(self):
        self._thread.start()

    def join(self, timeout=None):
        self._thread.join(timeout)

    def isAlive(self):
        return self._thread.isAlive()

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
        if relay:
            self.log.debug("cooling relay set to {}".format(relay.name))
        else:
            self.log.debug("cooling relay disabled")
        self._active_cooling_relay = relay

    @property
    def active_heating_relay(self):
        return self._active_heating_relay

    @active_heating_relay.setter
    def active_heating_relay(self, relay):
        if relay:
            self.log.debug("heating relay set to {}".format(relay.name))
        else:
            self.log.debug("heating relay disabled")
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
