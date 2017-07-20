"""
Implement classes for logging data to a carbon time-series database.
"""
import numbers
import socket
import platform
import time

from . import DataSource

def set_keepalive_linux(sock, after_idle_sec=15, interval_sec=15, max_fails=5):
    """Set TCP keepalive on an open socket.

    It activates after 1 second (after_idle_sec) of idleness,
    then sends a keepalive ping once every 3 seconds (interval_sec),
    and closes the connection after 5 failed ping (max_fails), or 15 seconds
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)

def set_keepalive_osx(sock, after_idle_sec=15, interval_sec=15, max_fails=5):
    """Set TCP keepalive on an open socket.

    sends a keepalive ping once every interval_sec seconds
    """
    TCP_KEEPALIVE = 0x10
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, TCP_KEEPALIVE, interval_sec)

class CarbonDataSource(DataSource):
    """
    Class implementation used to set data into a carbon database. Does not
    implement gets because graphite is used for that.
    """

    def __init__(self, name, **kwargs):
        """
        Requires these additional kwargs:

        - host
        - port: optional [default: 2003]
        - socket_timeout: optional, [default: 5 seconds]
        - enable_keepalive: optional, boolean, Linux/OSX only [default: True]
        """
        super(CarbonDataSource, self).__init__(name, **kwargs)
        self._config = kwargs
        try:
            self.host = kwargs['host']
        except KeyError:
            raise RuntimeError("host must be provided")
        try:
            self.port = kwargs['port']
        except KeyError:
            self.port = 2003
        try:
            self.timeout = kwargs['socket_timeout']
        except KeyError:
            self.timeout = 5.0
        try:
            self.enable_keepalive = kwargs['enable_keepalive']
        except KeyError:
            self.enable_keepalive = True
        self.__socket = None

    @property
    def socket(self):
        """
        Returns the current socket
        """
        if not self.__socket:
            self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__socket.settimeout(self.timeout)
            if self.enable_keepalive:
                if platform.system() == "Linux":
                    set_keepalive_linux(self.__socket)
                elif platform.system() in ("Darwin",):
                    set_keepalive_osx(self.__socket)
            try:
                self.__socket.connect((self.host, self.port))
            except socket.gaierror as err:
                self.log.error("Error connecting: %s", err.__str__())
        return self.__socket

    def set(self, key, value, timestamp=None):
        """
        Given an iterable key consisting of path elements (things that would be
        separated by dots in graphite), and a value, set the value into carbon
        with a current timestamp. Optionally, provide a timestamp.

        Note, `value` must be a number.
        """
        if not isinstance(value, numbers.Number):
            raise RuntimeError("bad data for logging to carbon: %s", value)
        if timestamp is None:
            timestamp = time.time()
        key = '.'.join(key)
        self._send(key, value, timestamp)

    def _send(self, key, value, timestamp):
        """
        Implement the low-level socket send operation
        """
        payload = "{} {} {}\n".format(key, value, int(timestamp)).encode()
        try:
            self.socket.send(payload)
        except OSError as err:
            self.log.error("Error while writing to carbon: %s", err.__str__())
