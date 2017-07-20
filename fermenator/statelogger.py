"""
This module houses classes for logging the state of heating, cooling, etc to
one or more datasources.
"""
import time

class StateLogger:
    """
    This abstract class defines the API for logging state to a datasource.
    """

    def __init__(self, name, **kwargs):
        """
        You must pass this class a name and one or more of the following kwargs:

        - datasource: the datasource object to log to
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

    def log_heartbeat(self, obj):
        """
        Log a heartbeat to the datasource for a specific object.
        """
        raise NotImplementedError()

    def log_cooling_on(self, obj):
        """
        Given an object, log that cooling has turned on. Must be implemented
        in a subclass specific to a datasource.
        """
        raise NotImplementedError()

    def log_cooling_off(self, obj):
        """
        Given an object, log that cooling has turned off. Must be implemented
        in a subclass specific to a datasource.
        """
        raise NotImplementedError()

    def log_heating_on(self, obj):
        """
        Given an object, log that heating has turned on. Must be implemented
        in a subclass specific to a datasource.
        """
        raise NotImplementedError()

    def log_heating_off(self, obj):
        """
        Given an object, log that heating has turned off. Must be implemented
        in a subclass specific to a datasource.
        """
        raise NotImplementedError()

class FirebaseStateLogger(StateLogger):
    """
    Implement the methods to log state to firebase.
    """

    def __init__(self, name, **kwargs):
        """
        Requires the same args as :class:`StateLogger`, as well as the following:

        - base_path: a dot-separated string path to log to within firebase
        """
        super(FirebaseStateLogger, self).__init__(name, **kwargs)
        try:
            self.base_path = kwargs['base_path'].split('.')
        except KeyError:
            raise RuntimeError("base_path must be defined")

    def log_heartbeat(self, obj):
        """
        Logs the current timestamp to the datasource at `base_path` + obj.name +
        "heartbeat"
        """
        self.datasource.set(self.base_path + (obj.name, "cooling"), time.time())

    def log_cooling_on(self, obj):
        """
        Write a `1` to the firebase datasource at `base_path` + obj.name +
        "cooling"
        """
        self.datasource.set(self.base_path + (obj.name, "cooling"), 1)

    def log_cooling_off(self, obj):
        """
        Write a `0` to the firebase datasource at `base_path` + obj.name +
        "cooling"
        """
        self.datasource.set(self.base_path + (obj.name, "cooling"), 0)

    def log_heating_on(self, obj):
        """
        Write a `1` to the firebase datasource at `base_path` + obj.name +
        "heating"
        """
        self.datasource.set(self.base_path + (obj.name, "heating"), 1)

    def log_cooling_off(self, obj):
        """
        Write a `0` to the firebase datasource at `base_path` + obj.name +
        "heating"
        """
        self.datasource.set(self.base_path + (obj.name, "heating"), 0)

class CarbonStateLogger(StateLogger):
    """
    Log state data to a carbon time-series database.
    """

    
