import pyrebase
import logging
from . import DataSource, DataNotFoundError
from fermenator.conversions import temp_c_to_f, sg_to_plato, unix_timestmap_to_datetime

class FirebaseDataSource(DataSource):

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
        self._config = kwargs
        self._fb_hndl = None
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__, name))

    @property
    def _handle(self):
        if not self._fb_hndl:
            self._fb_hndl = pyrebase.initialize_app(self._config).database()
        return self._fb_hndl

    def get(self, key):
        """
        Get the datastructure from firebase at key (path)
        """
        keypath = '/' + '/'.join(key) + '/'
        res = self._handle.child(keypath).get().val()
        if type(res) == 'NoneType':
            raise DataNotFoundError('no data found at key {}'.format(keypath))
        return res

class BrewConsoleFirebaseDS(FirebaseDataSource):

    def __init__(self, name, **kwargs):
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
        super(self.__class__, self).__init__(name, **kwargs)

    def get_gravity(self, identifier):
        """
        Returns the most recent gravity reading for the item at `identifier`
        """
        val = super(self.__class__, self).get(
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
        # TODO: use different temperture source
        val = super(self.__class__, self).get(
            ('brewery', identifier, 'readings', 'tilt_temperature'))
        rdata = dict()
        rdata['timestamp'] = unix_timestmap_to_datetime(val['timestamp'])
        rdata['temperature'] = float(val['value'])  # celcius
        if self.temperature_unit == 'F':
            rdata['temperature'] = temp_c_to_f(rdata['temperature'])
        return rdata
