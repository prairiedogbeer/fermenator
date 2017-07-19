"""
Represents objects that we interact with over the i2c bus, including wrapping
objects for thread safety, etc.
"""
import threading
import Adafruit_GPIO
import Adafruit_GPIO.MCP230xx

class MCP23017():
    """
    This represents an MCP23017 I2C-based GPIO expansion IC, used to add more
    GPIO ports to a Raspberry Pi, etc. It wraps the Adafruit version of this
    object type, making it into a singleton and ensuring that all operations
    against the chip are mutually exclusive (avoiding colissions).
    """
    __lock = threading.Lock()
    __instance = None

    def __init__(self, *args, **kwargs):
        """
        Takes the exact same arguments as :class:`Adafruit_GPIO.MCP230xx.MCP23017`.
        """
        with MCP23017.__lock:
            if MCP23017.__instance is None:
                MCP23017.__instance = Adafruit_GPIO.MCP230xx.MCP23017.__new__(
                    self, *args, **kwargs
                )

    def _call_protected_function(self, function, *args, **kwargs):
        """
        function must be callable
        """
        with MCP23017.__lock:
            return function(*args, **kwargs)

    def __getattr__(self, name):
        with MCP23017.__lock:
            subattr = MCP23017.__instance.__getattr__(name)
            if callable(subattr):
                def fn(*args, *kwargs):
                    with MCP23017.__lock:
                        return subattr(*args, **kwargs)
                return fn
            return subattr
