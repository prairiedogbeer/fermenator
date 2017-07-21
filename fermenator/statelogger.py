"""
This module houses classes for logging the state of heating, cooling, etc to
datasources.
"""
import logging
import time

class StateLogger:
    """
    Implement the methods to log state to firebase.
    """

    def __init__(self, name, **kwargs):
        """
        You must pass this class a name and one or more of the following kwargs:

        - datasource: the datasource object to log to
        - path_prefix: a dot-separated string path to log to within datasource
        - enable_logging: optional - toggle logging to the datasource (boolean)
        """
        try:
            self.datasource = kwargs['datasource']
        except KeyError:
            raise RuntimeError("datasource must be configured")
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__, name))
        self._config = kwargs
        try:
            self.path_prefix = tuple(kwargs['path_prefix'].split('.'))
        except KeyError:
            raise RuntimeError("path_prefix must be defined")
        try:
            self.enabled = kwargs['enable_logging']
        except KeyError:
            self.enabled = True

    def log_heartbeat(self, obj):
        """
        Logs the current timestamp to the datasource at `path_prefix` + obj.name +
        "heartbeat"
        """
        if self.enabled:
            self.log.debug("logging heartbeat")
            self.datasource.set(
                self.path_prefix + (obj.name, "heartbeat"), time.time())

    def log_cooling_on(self, obj):
        """
        Write a `1` to the firebase datasource at `path_prefix` + obj.name +
        "cooling"
        """
        if self.enabled:
            self.log.debug("logging cooling on")
            self.datasource.set(self.path_prefix + (obj.name, "cooling"), 1)

    def log_cooling_off(self, obj):
        """
        Write a `0` to the firebase datasource at `path_prefix` + obj.name +
        "cooling"
        """
        if self.enabled:
            self.log.debug("logging cooling off")
            self.datasource.set(self.path_prefix + (obj.name, "cooling"), 0)

    def log_heating_on(self, obj):
        """
        Write a `1` to the firebase datasource at `path_prefix` + obj.name +
        "heating"
        """
        if self.enabled:
            self.log.debug("logging heating on")
            self.datasource.set(self.path_prefix + (obj.name, "heating"), 1)

    def log_heating_off(self, obj):
        """
        Write a `0` to the firebase datasource at `path_prefix` + obj.name +
        "heating"
        """
        if self.enabled:
            self.log.debug("logging heating off")
            self.datasource.set(self.path_prefix + (obj.name, "heating"), 0)
