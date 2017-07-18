"""
This module contains :class:`Relay`-type objects, which represent actual Relay
devices used to enable or disable heating and cooling of beers.
"""
import logging
import gpiozero
import Adafruit_GPIO
import Adafruit_GPIO.MCP230xx

ON = 1
OFF = 0

class Relay(object):
    """
    Implements a relay object that can be turned on or off. This version of the
    object doesn't actually control any relays, more-or-less acting as a mock
    relay. Extend this class to control specific hardware architectures.
    """

    def __init__(self, name, **kwargs):
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__, self.__class__.__name__,
                name))
        self._config = kwargs
        self.name = name
        self._state = None

    def __del__(self):
        self.log.debug("destructing")
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
        super(GPIORelay, self).__init__(name, **kwargs)
        if "gpio_pin" not in kwargs:
            raise RuntimeError("No gpio_pin specified in relay configuration")
        try:
            active_high = kwargs['active_high']
        except KeyError:
            active_high = True
        self._device = gpiozero.DigitalOutputDevice(
            pin=int(self._config['gpio_pin']),
            active_high=active_high,
            initial_value=False # keep relay turned off initially
        )
        if 'duty_cycle' in kwargs:
            if 'cycle_time' in kwargs:
                self._duty_cycle = float(kwargs['duty_cycle'])
                self._cycle_time = float(kwargs['cycle_time'])
            else:
                self.log.warning(
                    "duty_cycle specified without cycle_time. Ignoring duty_cycle")
                self._duty_cycle = None
        else:
            self._duty_cycle = None
        self.off()

    def on(self):
        """
        Turn on the relay at the GPIO pin associated with the instance.
        """
        super(GPIORelay, self).on()
        if self._duty_cycle:
            on_time = self._duty_cycle * self._cycle_time
            off_time = self._cycle_time - on_time
            self._device.blink(on_time=on_time, off_time=off_time)
        else:
            self._device.on()

    def off(self):
        """
        Turn off the relay at the GPIO pin associated with the instance.
        """
        super(GPIORelay, self).off()
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

        """
        super(MCP23017Relay, self).__init__(name, **kwargs)
        if "mx_pin" not in kwargs:
            raise RuntimeError("No gpio_pin specified in relay configuration")
        try:
            self.mx_pin = kwargs['mx_pin']
        except KeyError:
            raise RuntimeError("mx_pin must be provided")
        try:
            self.high_signal = kwargs['active_high']
        except KeyError:
            self.high_signal = True
        try:
            self.i2c_addr = kwargs['i2c_addr']
        except KeyError:
            self.i2c_addr = 0x20
        self._device = Adafruit_GPIO.MCP230xx.MCP23017(
            self.i2c_addr
        )
        self._device.setup(self.mx_min, Adafruit_GPIO.OUT)
        self.off()

    def on(self):
        """
        Turn on the relay, taking into account active_high configuration.
        """
        super(MCP23017Relay, self).on()
        self._device.output(self.mx_pin), self.high_signal)

    def off(self):
        """
        Turn off the relay, taking into account active_high configuration.
        """
        super(MCP23017Relay, self).off()
        self._device.output(self.mx_pin, not self.high_signal)
