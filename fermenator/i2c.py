"""
Represents objects that we interact with over the i2c bus, including wrapping
objects for thread safety, etc.
"""
import logging
import threading
import time
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
                if 'i2c_interface' not in kwargs:
                    try:
                        # The default i2c interface for Adafruit is their
                        # experimental Pure_IO module, which they freely admit is
                        # buggy and incomplete. Use SMBus if it is available.
                        import smbus
                        kwargs['i2c_interface'] = smbus.SMBus
                    except ImportError:
                        pass
                MCP23017.__instance = Adafruit_GPIO.MCP230xx.MCP23017(
                    *args, **kwargs
                )
                for port in range(0, MCP23017.__instance.NUM_GPIO):
                    MCP23017.__instance.setup(port, Adafruit_GPIO.OUT)
                MCP23017.__instance.GPIO = 0x14

    def output(self, *args, **kwargs):
        """
        Workaround because sometimes the state on the MCP23017 gets messed up
        and we need to reconfigure the port output directions for everything
        to work correctly
        """
        self._write_output(*args, **kwargs)
        self._write_iodir()

    def _write_output(self, *args, **kwargs):
        """
        Sometimes sending commands over the bus too quickly causes
        OSError I/O Exceptions. Add some delay/retry on outputs
        """
        last_err = None
        for iter in range(0, 3):
            time.sleep(0.05)
            try:
                MCP23017.__instance.output(*args, **kwargs)
            except OSError as error:
                if error.errno == 121 and iter < 3:
                    pass
                else:
                    raise

    def _write_iodir(self):
        """
        Sometimes sending commands over the bus too quickly causes
        OSError I/O Exceptions. Add some delay/retry
        """
        last_err = None
        for iter in range(0, 3):
            time.sleep(0.05)
            try:
                MCP23017.__instance.write_iodir()
            except OSError as error:
                if error.errno == 121 and iter < 3:
                    pass
                else:
                    raise

    def __getattr__(self, name):
        with MCP23017.__lock:
            subattr = getattr(MCP23017.__instance, name)
            if callable(subattr):
                def fn(*args, **kwargs):
                    with MCP23017.__lock:
                        return subattr(*args, **kwargs)
                return fn
            return subattr
