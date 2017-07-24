"""
This module contains :class:`Relay`-type objects, which represent actual Relay
devices used to enable or disable heating and cooling of beers.
"""
import logging
import time
import gpiozero
import gpiozero.threads
import fermenator.i2c
from .exception import ConfigurationError
import Adafruit_GPIO

ON = 1
OFF = 0

class Relay(object):
    """
    Implements a relay object that can be turned on or off. This version of the
    object doesn't actually control any relays, more-or-less acting as a mock
    relay. Extend this class to control specific hardware architectures.
    """

    def __init__(self, name, **kwargs):
        """
        The following kwargs are supported:

        - minimum_off_time: optional [default: 0]
        - duty_cycle: an optional decimal fraction representing the percentage
          of on time
        - cycle_time: the overall duration of each duty cycle, in seconds,
          required if `duty_cycle` is specified
        - active_high: boolean, True by default

        The `minimum_off_time` parameter allow you to
        prevent a relay from turning off and on too quickly for whatever the
        underlying device supports. For example, a compressor needs a minimum
        of five minutes of off time between cycles, so you should set
        `minimum_off_time` to 300 seconds.

        ..note::

            minimum_off_time is respected at relay instantiation, meaning that
            if you set this value, a relay won't turn on until after this time
            has elapsed after starting fermenator. Also, if you specify both a
            duty cycle and a minimum off time, the minimum off time is only
            respected for the initial time period, then the duty cycle config
            takes over.

        """
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__, self.__class__.__name__,
                name))
        self._config = kwargs
        self.name = name
        self._state = None
        try:
            self._duty_cycle = float(kwargs['duty_cycle'])
            self._cycle_time = float(kwargs['cycle_time'])
        except KeyError:
            self.log.debug("No duty cycle configured")
            self._duty_cycle = None
        try:
            self.minimum_off_time = float(kwargs['minimum_off_time'])
        except KeyError:
            self.minimum_off_time = 0.0
        try:
            self.high_signal = kwargs['active_high']
        except KeyError:
            self.high_signal = True
        self._last_off_time = None
        self._duty_cycle_thread = None
        self._last_off_time = time.time()
        self.off()

    def __del__(self):
        self.off()

    def on(self):
        """
        Turn on the relay, taking into account active_high configuration.
        Supports running the relay in a duty cycle.
        """
        if self._duty_cycle_thread:
            if self._duty_cycle_thread.is_alive():
                self.log.debug("on called but duty cycle thread already running")
                return
            else:
                self.log.warning("duty cycle thread died and will be restarted")
                self.off()
        self._duty_cycle_thread = gpiozero.threads.GPIOThread(
            target=self._run_duty_cycle)
        self._duty_cycle_thread.start()

    def _on_hook(self):
        """
        This hook is called whenever the relay is switched on, and actually
        performs the low-level function of switching on the device
        """
        self.log.debug("switching on")
        self._state = ON

    def off(self):
        "Turns off the relay"
        if self._duty_cycle_thread:
            self.log.debug("shutting down relay duty_cycle thread")
            self._stop_duty_cycle()
        self._off_hook()

    def _off_hook(self):
        """
        This hook is called whenever the relay is switched off, and actually
        performs the low-level function of switching the relay off
        """
        if self._state != OFF:
            # Only change _last_off_time when actually turning off a relay.
            # You can call off() while a relay is in off-state part of duty cycle
            # and don't have to wait a full minimum_off_time before turning on.
            self._last_off_time = time.time()
            self.log.debug("switching off")
            self._state = OFF

    def is_on(self):
        """
        Returns True if the relay state is on, False otherwise.
        """
        if self._state == ON:
            return True
        return False

    def is_off(self):
        """
        Returns True if the relay state is on, False otherwise.
        """
        if self._state == OFF:
            return True
        return False

    def _stop_duty_cycle(self):
        """
        Stops any running duty cycle threads
        """
        if self._duty_cycle_thread:
            self._duty_cycle_thread.stop()
            self._duty_cycle_thread = None

    def _run_duty_cycle(self):
        """
        This method makes the relay turn on and off in an infinite loop, using
        the specified duty cycle config. Meant to be passed to a Thread
        object and run in the background.
        """
        remaining_time = self._last_off_time + self.minimum_off_time - time.time()
        if remaining_time > 0:
            self.log.info(
                "waiting %ds for minimum_off_time to expire before turning on",
                remaining_time)
            if self._duty_cycle_thread.stopping.wait(timeout=remaining_time):
                return
        else:
            self.log.info("duty cycle thread starting")
        on_time = None
        off_time = None
        if self._duty_cycle:
            on_time = self._duty_cycle * self._cycle_time
            off_time = self._cycle_time - on_time
        while True:
            self._on_hook()
            if self._duty_cycle_thread.stopping.wait(timeout=on_time):
                break
            self._off_hook()
            if self._duty_cycle_thread.stopping.wait(timeout=off_time):
                break

class GPIORelay(Relay):
    """
    Implement relay as a GPIO Device such as would be connected to a
    Raspberry Pi. Adds support for duty cycling the relay rather than keeping
    it running continuously in the on phase, which may be useful with hardware
    capable of inducing rapid temperature changes in a short period of time
    (where the user wants to slow down the temperature change).
    """

    def __init__(self, name, **kwargs):
        """
        Same as :class:`Relay`, but also requires kwarg `gpio_pin`, which
        refers to the GPIO pin number connected to the relay. Optionally,
        pass a `duty_cycle` and `cycle_time` parameter to enable duty-cycling
        of the relay. `duty_cycle` should be a floating-point percentage of on time
        and `cycle_time` should be the total time for each duty cycle in
        floating-point seconds. You can also provide `active_high` (boolean) to
        determine whether or not the relay will be sent a high (1) signal to
        turn on, or a low(0), defaults to True.

        .. warning::

            This class has no error checking for duty cycle config. If you use
            short cycle times you could, at the very least, prematurely wear out
            your relay, or do much worse to anything connected on the other side
            of it (such as refrigeration units). Use at your own risk.

        """
        if "gpio_pin" not in kwargs:
            raise ConfigurationError(
                "No gpio_pin specified in relay configuration")
        self._device = gpiozero.DigitalOutputDevice(
            pin=int(kwargs['gpio_pin']),
            active_high=kwargs['active_high'],
            initial_value=False # keep relay turned off initially
        )
        super(GPIORelay, self).__init__(name, **kwargs)

    def _on_hook(self):
        "Actually sends the low-level `on` signal to the relay"
        super(GPIORelay, self)._on_hook()
        self._device.on()

    def _off_hook(self):
        "Sends the low-level signal to turn off the relay"
        super(GPIORelay, self)._off_hook()
        try:
            self._device.off()
        except AttributeError:
            pass

class MCP23017Relay(Relay):
    """
    Implements a :class:`Relay` connected to a GPIO expansion IC, the
    MC23017Y. The MC23017 sits on the I2C bus and implements a simple GPIO-like
    interface.
    """

    def __init__(self, name, **kwargs):
        """
        Provide the following kwargs:

        - mx_pin: The pin # on the MCP23017 that controls the relay
        - i2c_addr: Set the address of the MCP23017 on the i2c bus [default: 0x20]
        - active_high: whether or not setting the pin high activates the relay
          [default: True]
        - duty_cycle: a percentage of on time
        - cycle_time: a duration of time for entire duty cycle

        """
        if "mx_pin" not in kwargs:
            raise ConfigurationError(
                "No gpio_pin specified in relay configuration")
        try:
            self.mx_pin = kwargs['mx_pin']
        except KeyError:
            raise ConfigurationError("mx_pin must be provided")
        try:
            self.i2c_addr = kwargs['i2c_addr']
        except KeyError:
            self.i2c_addr = 0x20
        self._device = fermenator.i2c.MCP23017(
            self.i2c_addr
        )
        self._device.setup(self.mx_pin, Adafruit_GPIO.OUT)
        super(MCP23017Relay, self).__init__(name, **kwargs)

    def _on_hook(self):
        "Actually sends the low-level `on` signal to the relay"
        super(MCP23017Relay, self)._on_hook()
        self._device.output(self.mx_pin, self.high_signal)

    def _off_hook(self):
        "Sends the low-level signal to turn off the relay"
        super(MCP23017Relay, self)._off_hook()
        try:
            self._device.output(self.mx_pin, not self.high_signal)
        except AttributeError:
            pass
