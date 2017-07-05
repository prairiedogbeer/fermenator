import pyrebase
from . import DataSource, DataNotFoundError
from fermenator.conversions import temp_c_to_f, sg_to_plato

class FirebaseDataSource(DataSource):

    def __init__(self, **kwargs):
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

    @property
    def _handle(self):
        if not self._fb_hndl:
            self._fb_hndl = pyrebase.initialize_app(self._config).database()
        return self._fb_hndl

    def get(self, key):
        """
        Get the datastructure from firebase at key (path)
        """
        # TODO: THis is bad code and can result in multiple slashes
        keypath = '/' + '/'.join(key) + '/'
        res = self._handle.child(keypath).get().val()
        if type(res) == 'NoneType':
            raise DataNotFoundError('no data found at key {}'.format(keypath))
        return res

class BrewConsoleFirebaseDS(FirebaseDataSource):

    def __init__(self, **kwargs):
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
        super(self.__class__, self).__init__(**kwargs)


    def get_gravity(self, batch_id):
        """
        Returns the most recent gravity reading for the batch
        """
        val = super(self.__class__, self).get(
            ('brewery', batch_id, 'readings', 'gravity'))
        grav = float(val['value'])/1000.0
        if self.gravity_unit == 'P':
            return sg_to_plato(grav)
        return grav

    def get_temperature(self, batch_id):
        """
        Returns the most recent temperture reading for the batch
        """
        # TODO: use different temperture source
        val = super(self.__class__, self).get(
            ('brewery', batch_id, 'readings', 'tilt_temperature'))
        temp = float(val['value'])
        if self.temperature_unit == 'F':
            return temp_c_to_f(temp)
        return temp
