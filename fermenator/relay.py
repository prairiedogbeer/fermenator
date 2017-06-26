import logging

ON = 1
OFF = 0

class Relay(object):
    """
    Implements a relay object that can be turned on or off, including running
    with a duty cycle (eg 50%%, such that relay turns on and off 50%% of the
    time). This version of the object doesn't actually control any relays,
    more-or-less acting as a mock relay. Extend this class to control specific
    hardware.
    """

    def __init__(self, name, **kwargs):
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__, self.__class__.__name__,
                name))
        self._config = kwargs
        self.name = name
        self._state = None
        self.off()

    def __destroy__(self):
        self.log.debug("__destroy__ called")
        self.off()

    def on(self):
        "Turns on the relay"
        if self._state != ON:
            self.log.info("turning on")
            self._state = ON

    def off(self):
        "Turns off the relay"
        if self._state != OFF:
            self.log.info("turning off")
            self._state = OFF

    def is_on(self):
        if self._state == ON:
            return True
        return False

    def is_off(self):
        if self._state == OFF:
            return True
        return False
