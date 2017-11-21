"""
This package includes the firebase-related classes which act as datasources for
configuration or beer data.
"""
import threading
import ssl
import urllib3.exceptions
import pyrebase
import requests.exceptions
from fermenator.conversions import (
    temp_c_to_f, sg_to_plato, unix_timestmap_to_datetime)
from fermenator.exception import (
    DataFetchError, DataWriteError, DSConnectionError)
from . import DataSource

class FirebaseDataSource(DataSource):
    """
    Implement a :class:`fermenator.datasource.DataSource` object that provides
    the general methods for accessing firebase.
    """
    __lock = threading.RLock()

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
        self._fb_hndl = None

    @property
    def _handle(self):
        """
        Returns an instance of the firebase database object. Caches the object
        locally after the first retrieval.
        """
        with FirebaseDataSource.__lock:
            if not self._fb_hndl:
                self.log.debug("getting new firebase handle")
                try:
                    self._fb_hndl = pyrebase.initialize_app(
                        self._config).database()
                except (requests.exceptions.HTTPError, ssl.SSLError,
                        urllib3.exceptions.SSLError) as err:
                    self._fb_hndl = None
                    raise DSConnectionError(
                        "connect to firebase failed: {}".format(err))
            return self._fb_hndl

    def get(self, key):
        """
        Get the datastructure from firebase at key (path)
        """
        keypath = '/' + '/'.join(key) + '/'
        with FirebaseDataSource.__lock:
            try:
                res = self._handle.child(keypath).get().val()
                if res is None:
                    raise DataFetchError('no data found at key {}'.format(keypath))
                return res
            except (requests.exceptions.HTTPError, ssl.SSLError,
                    urllib3.exceptions.SSLError) as err:
                self._fb_hndl = None
                raise DataFetchError("read from firebase failed: {}".format(err))

    def set(self, key, value):
        """
        Set a key-value pair in Firebase. Key must be an iterable of keys
        to traverse in the tree, and value can be a dict, float, int, etc.
        """
        with FirebaseDataSource.__lock:
            try:
                obj = self._handle
                for subkey in key:
                    obj = obj.child(subkey)
                obj.set(value)
            except (requests.exceptions.HTTPError, ssl.SSLError,
                    urllib3.exceptions.SSLError) as err:
                self._fb_hndl = None
                raise DataWriteError("write to firebase failed: {}".format(err))

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
        - temperature_key_name: optional [default: 1w_temperature]
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
        try:
            self.temperature_key_name = kwargs['temperature_key_name']
        except KeyError:
            self.temperature_key_name = '1w_temperature'

    def get_gravity(self, identifier):
        """
        Returns the most recent gravity reading for the item at `identifier`
        """
        val = self.get(
            ('brewery', identifier, 'readings', 'gravity'))
        rdata = dict()
        rdata['timestamp'] = unix_timestmap_to_datetime(
            val['timestamp'])
        rdata['gravity'] = float(val['value'])/1000.0
        if self.gravity_unit == 'P':
            rdata['gravity'] = sg_to_plato(rdata['gravity'])
        return rdata

    def get_temperature(self, identifier):
        """
        Returns the most recent temperture reading for the item at `identifier`
        """
        val = self.get(
            ('brewery', identifier, 'readings',
             self.temperature_key_name))
        rdata = dict()
        rdata['timestamp'] = unix_timestmap_to_datetime(
            val['timestamp'])
        rdata['temperature'] = float(val['value'])  # celcius
        if self.temperature_unit == 'F':
            rdata['temperature'] = temp_c_to_f(rdata['temperature'])
        return rdata
