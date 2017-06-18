import logging

class AbsractBeer(object):
    """
    Represents beer sitting in a fermenter or other temperature-controlled
    vessel. The primary purpose of this class is to implement functions that
    determine if the beer needs heating or cooling. This class is designed
    to be subclassed for specific recipes such that fermentation algorithms
    can be programmed.
    """

    def __init__(self, name):
        self._name = name
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

    def __init__(self, name, datasource, threshold=0.5):
        self.datasource = datasource
        self._threshold = threshold
        self._set_point = None
        super(SetPointBeer, self).__init__(name)

    @property
    def set_point(self):
        return self._set_point

    @set_point.setter
    def set_point(self, value):
        self._set_point = value

    @property
    def threshold(self):
        return self._threshold

    @threshold.setter
    def threshold(self, value):
        self._threshold = value

    def get_current_temperature(self):
        return self.datasource.get_key('temperature')

    def requires_heating(self):
        if self.set_point is None:
            return False
        temp = self.get_current_temperature()
        if self.set_point > (temp + self.threshold):
            self.log.info(
                "heating required (temp={}, set_point={}, threshold={})".format(
                    temp, self.set_point, self.threshold))
            return True

    def requires_cooling(self):
        if self.set_point is None:
            return False
        temp = self.get_current_temperature()
        if (self.set_point + self.threshold) < temp:
            self.log.info(
                "cooling required (temp={}, set_point={}, threshold={})".format(
                    temp, self.set_point, self.threshold))
            return True
