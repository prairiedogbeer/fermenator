"""
This package includes the firebase-related classes which act as datasources for
configuration or beer data.
"""
import logging
import pyrebase
from fermenator.conversions import (
    temp_c_to_f, sg_to_plato, unix_timestmap_to_datetime)
from . import DataSource, DataNotFoundError

class FirebaseDataSource(DataSource):
    """
    Implement a :class:`fermenator.datasource.DataSource` object that provides
    the general methods for accessing firebase.
    """

    def __init__(self, name, **kwargs):
        """
        Config should be whatever needs to be passed to the firebase
        app config, eg::

            kwargs = {
              "apiKey": "apiKey",
              "authDomain": "projectId.firebaseapp.com",
              "databaseURL": "https://databaseName.firebaseio.com",
              "storageBucket": "projectId.appspot.com",
              "serviceAccount": "path/to/serviceAccountCredentials.json"
            }

        """
        super(FirebaseDataSource, self).__init__(name, **kwargs)
        self._config = kwargs
        self._fb_hndl = None
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__, name))

    @property
    def _handle(self):
        """
        Returns an instance of the firebase database object. Caches the object
        locally after the first retrieval.
        """
        if not self._fb_hndl:
            self._fb_hndl = pyrebase.initialize_app(self._config).database()
        return self._fb_hndl

    def get(self, key):
        """
        Get the datastructure from firebase at key (path)
        """
        keypath = '/' + '/'.join(key) + '/'
        res = self._handle.child(keypath).get().val()
        if res is None:
            raise DataNotFoundError('no data found at key {}'.format(keypath))
        return res

class BrewConsoleFirebaseDS(FirebaseDataSource):
    """
    Implements a version of the :class:`FirebaseDataSource` class that provides
    wrappers and logic specific to beer data stored within, such as the path
    to gravity and temperature data, timestamp handling, etc.
    """

    def __init__(self, name, **kwargs):
        """
        This class requires all the same arguments as
        :class:`FirebaseDataSource`, but adds the following:

        - gravity_unit (P or SG)
        - temperature_unit (C or F)
        """
        super(BrewConsoleFirebaseDS, self).__init__(name, **kwargs)
        try:
            self.gravity_unit = kwargs['gravity_unit'].upper()
            del kwargs['gravity_unit']
        except KeyError:
            self.gravity_unit = 'P'
        try:
            self.temperature_unit = kwargs['temperature_unit'].upper()
            del kwargs['temperature_unit']
        except KeyError:
            self.temperature_unit = 'C'

    def get_gravity(self, identifier):
        """
        Returns the most recent gravity reading for the item at `identifier`
        """
        val = super(BrewConsoleFirebaseDS, self).get(
            ('brewery', identifier, 'readings', 'gravity'))
        rdata = dict()
        rdata['timestamp'] = unix_timestmap_to_datetime(val['timestamp'])
        rdata['gravity'] = float(val['value'])/1000.0
        if self.gravity_unit == 'P':
            rdata['gravity'] = sg_to_plato(rdata['gravity'])
        return rdata

    def get_temperature(self, identifier):
        """
        Returns the most recent temperture reading for the item at `identifier`
        """
        val = super(BrewConsoleFirebaseDS, self).get(
            ('brewery', identifier, 'readings', 'tilt_temperature'))
        rdata = dict()
        rdata['timestamp'] = unix_timestmap_to_datetime(val['timestamp'])
        rdata['temperature'] = float(val['value'])  # celcius
        if self.temperature_unit == 'F':
            rdata['temperature'] = temp_c_to_f(rdata['temperature'])
        return rdata
