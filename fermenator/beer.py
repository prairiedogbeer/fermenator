import logging
import datetime

class AbstractBeer(object):
    """
    Represents beer sitting in a fermenter or other temperature-controlled
    vessel. The primary purpose of this class is to implement functions that
    determine if the beer needs heating or cooling. This class is designed
    to be subclassed for specific recipes such that fermentation algorithms
    can be programmed.
    """

    def __init__(self, name):
        self._name = name.upper().strip()
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                self._name))

    @property
    def name(self):
        """
        Hiding the name of the beer so that it is read-only after instantiation
        """
        return self._name

    def requires_heating(self):
        pass

    def requires_cooling(self):
        pass


class SetPointBeer(AbstractBeer):
    """
    This version of :class:`AbstractBeer` implements a "dumb" set-point
    approach like you'd find on an STC-1000.
    """

    def __init__(self, name, datasource, set_point, threshold=0.5, data_age_warning_time=(30 * 60)):
        super(SetPointBeer, self).__init__(name)
        self.datasource = datasource
        self.set_point = set_point
        self.threshold = threshold
        self.data_age_warning_time = data_age_warning_time

    @property
    def set_point(self):
        return self._set_point

    @set_point.setter
    def set_point(self, value):
        self.log.info("configuring set point at {}".format(value))
        self._set_point = value

    @property
    def threshold(self):
        return self._threshold

    @threshold.setter
    def threshold(self, value):
        self.log.info("configuring set point threshold at {}".format(value))
        self._threshold = value

    def is_old_timestamp(self, timestamp):
        """
        Pass a timestamp to this function, it will return True if the date is
        older than the configured :attr:`data_age_warning_time`.
        """
        now = datetime.datetime.now()
        delta = now - timestamp
        if delta.total_seconds() >= self.data_age_warning_time:
            return True
        return False

    def _get_temperature_data(self):
        data = self.datasource.get((self.name, 'temperature')).next()
        if self.is_old_timestamp(data['timestamp']):
            raise RuntimeError(
                "no data for {} since {}".format(
                    self.name,
                    data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            ))
        return data['temperature']

    def requires_heating(self):
        """
        Returns True if the beer requires heating based on the set point,
        current temperature, and configured threshold, False otherwise. If
        data is older than the configured :attr:`data_age_warning_time`,
        returns False, ensuring that the beer is not accidentally heated.
        """
        if self.set_point is None:
            return False
        temp = self._get_temperature_data()
        if self.set_point > (temp + self.threshold):
            self.log.info(
                "heating required (temp={}, set_point={}, threshold={})".format(
                    temp, self.set_point, self.threshold))
            return True

    def requires_cooling(self):
        if self.set_point is None:
            return False
        temp = self._get_temperature_data()
        if (self.set_point + self.threshold) < temp:
            self.log.info(
                "cooling required (temp={}, set_point={}, threshold={})".format(
                    temp, self.set_point, self.threshold))
            return True
