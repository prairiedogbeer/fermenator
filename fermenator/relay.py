import logging

ON = 1
OFF = 0

class Relay(object):
    """
    Implements a relay object that can be turned on or off, including running
    with a duty cycle (eg 50%%, such that relay turns on and off 50%% of the
    time).
    """

    def __init__(self, hwaddr, name):
        self.log = logging.getLogger(
            "{}.{}.{}.{}".format(
                self.__class__.__module__, self.__class__.__name__,
                hwaddr, name))
        self.hwaddr = hwaddr
        self.name = name
        self.duty_cycle_pct = 100
        self.duty_cycle_on_time = 60    # seconds
        self.state = None
        self.off()

    def __destroy__(self):
        self.off()

    def on(self):
        "Turns on the relay"
        if self.state != ON:
            if self.duty_cycle_pct >= 100:
                self.log.debug("turning on")
                self.state = ON
            else:
                self.log.error("duty cycles not implemented yet")

    def off(self):
        "Turns off the relay"
        if self.state != OFF:
            self.log.debug("turning off")
            self.state = OFF

    def is_on(self):
        if self.state == ON:
            return True
        return False

    def is_off(self):
        if self.state == OFF:
            return True
        return False

    def __send_low_level_signal__(self, signal):
        "Send a low-level signal to the hardware address of this relay"
        self.log.debug("sending signal {} to hwaddr {}".format(signal, hwaddr))
