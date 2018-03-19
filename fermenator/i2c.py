"""
Represents objects that we interact with over the i2c bus, including wrapping
objects for thread safety, etc.
"""
import logging
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
    __lock = threading.RLock()
    __instance = None

    def __init__(self, *args, **kwargs):
        """
        Takes the exact same arguments as :class:`Adafruit_GPIO.MCP230xx.MCP23017`.
        """
        self.logger = logging.getLogger('fermenator.i2c.MCP23017')
        with MCP23017.__lock:
            if MCP23017.__instance is None:
                MCP23017.__instance = Adafruit_GPIO.MCP230xx.MCP23017(
                    *args, **kwargs
                )
                for port in range(0, MCP23017.__instance.NUM_GPIO):
                    MCP23017.__instance.setup(port, Adafruit_GPIO.OUT)
                MCP23017.__instance.GPIO = 0x14

    def write_gpio(self, *args, **kwargs):
        """
        Workaround because sometimes the state on the MCP23017 gets messed up
        and we need to reconfigure the port output directions for everything
        to work correctly
        """
        super(MCP23017, self).write_gpio(*args, **kwargs)
        self.logger.debug("about to write iodir")
        self.write_iodir()

    def __getattr__(self, name):
        with MCP23017.__lock:
            subattr = getattr(MCP23017.__instance, name)
            if callable(subattr):
                def fn(*args, **kwargs):
                    with MCP23017.__lock:
                        return subattr(*args, **kwargs)
                return fn
            return subattr
