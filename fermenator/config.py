import sys
import os.path
import time
from yaml import load as load_yaml
import logging

from fermenator.datasource.gsheet import *
from fermenator.datasource.firebase import *
from fermenator.relay import *
from fermenator.beer import *
from fermenator.manager import *

class ClassNotFoundError(RuntimeError):
    pass

def get_class_by_name(name):
    "Returns a configuration class by name (not an instance)"
    if name in ('GoogleSheetConfig', 'FirebaseConfig'):
        return globals()[name]
    raise ClassNotFoundError("no configuration class {} could be found".format(name))

def str_to_class(classname):
    return getattr(sys.modules[__name__], classname)

def sheet_data_to_dict(sheet_data):
    dict_config = dict()
    for row in sheet_data:
        item_name = row[0].strip()
        if not item_name:
            continue
        if not item_name in dict_config:
            dict_config[item_name] = {'config': dict()}
        key = row[1].lower().strip()
        value = row[2].strip()
        if key == 'type':
            dict_config[item_name][key] = value
        else:
            dict_config[item_name]['config'][key] = value
    return dict_config

class ConfigNotFoundError(RuntimeError):
    "Raise this exception when no configuration can be found/loaded"
    pass

class ConfigLoader():
    """
    Look for YaML configuration in local files, using the first file found,
    in the following order:

    - Locally provided config_file (from kwargs)
    - .fermenator (local directory)
    - ~/.fermenator/config (home directory)
    - /etc/fermenator/config (system configuration directory)

    Once config is found, parse it into a dictionary and expose config data
    through simple methods.
    """
    #: A tuple of default configuration file locations
    CONFIG_FILES = (
        '.fermenator', '~/.fermenator/config', '/etc/fermenator/config'
    )

    def __init__(self, config_file=None):
        self.log = logging.getLogger(
            "{}.{}".format(
            self.__class__.__module__,
            self.__class__.__name__))
        self.config_locations = self.CONFIG_FILES
        if config_file:
            self.config_locations = (config_file,)
        self._config = self._load()

    def _load(self):
        for location in self.config_locations:
            try:
                with open(os.path.expanduser(location)) as yfile:
                    self.log.info("loading configuration from {}".format(location))
                    return load_yaml(yfile)
            except FileNotFoundError:
                continue
        raise ConfigNotFoundError("No configuration could be found/loaded")

    def config(self):
        """
        Returns the configuration read from config files
        """
        # TODO: Make this return immutable data or a deep copy of the dict
        return self._config

class FermenatorConfig():
    """
    This class defines basic configuration methods for vivifying Relays, Beers,
    Managers, and DataSources from key-value pairs found in an abstract
    configuration DataSource.

    Pass in a 'refresh_interval' kwarg to set how often configuration will be
    checked for updates. If an update is found, the entire tree of managed
    objects will be torn down and rebuilt from the latest configuration. If
    no 'refresh_interval' is supplied, config will be checked every 5 minutes.
    """

    def __init__(self, name, **kwargs):
        self.log = logging.getLogger(
            "{}.{}.{}".format(
            self.__class__.__module__,
            self.__class__.__name__, name))
        self._config = kwargs
        self._relays = dict()
        self._beers = dict()
        self._managers = dict()
        self._datasources = dict()
        self.stop = False
        if 'refresh_interval' in kwargs:
            self.refresh_interval = float(kwargs['refresh_interval'])
        else:
            self.refresh_interval = 300.0

    def assemble(self):
        """
        Reads all the configuration and assembles objects in the correct order.
        """
        self.log.debug("assembling")
        self.get_relays()
        self.get_datasources()
        self.get_beers()
        self.get_managers()

    def disassemble(self):
        """
        Shuts down any running manager threads and destroys objects in the
        reverse order of creation.
        """
        self.log.debug("disassembling")
        for manager in self._managers.keys():
            self._managers[manager].stop()
            self._managers[manager].join(30.0)
            if self._managers[manager].isAlive():
                self.log.error("manager thread {} could not be stopped".format(manager))
                # TODO: deal with this problem smartly
        # force delete the reference to the old objects, should result
        # in a __destroy__ call on each
        for manager in self._managers.keys():
            del self._managers[manager]
        for beer in self._beers.keys():
            del self._beers[beer]
        for datasource in self._datasources.keys():
            del self._datasources[datasource]
        for relay in self._relays.keys():
            del self._relays[relay]

    def run(self):
        """
        Runs all manager threads and checks for updated configuration.
        When updated configuration is found, all existing manager threads
        are shut down and new ones are assembled and run.
        """
        try:
            while not self.stop:
                self.assemble()
                if not self._managers:
                    self.log.error("no managers found after assembly, nothing to do")
                    self.disassemble()
                    return None
                for manager in self._managers.keys():
                    self._managers[manager].start()
                fresh = True
                while fresh:
                    time.sleep(self.refresh_interval)
                    if not self.stop and self.is_config_changed():
                        self.log.info("detected new configuration data")
                        fresh = False
                self.disassemble()
        except KeyboardInterrupt:
            self.disassemble()

    def import_yaml_file(self, filename):
        raise NotImplementedError("import_yaml_file is not implemented for this config datasource")

    def is_config_changed(self):
        raise NotImplementedError("is_config_changed needs to be implemented in subclass")

    def get_relay_config(self):
        """
        Returns a dictionary containing a list of relays and their config
        values, eg::

            {
                'CoolingRelay1': {
                    'type': 'GPIORelay',
                    'pin': 1
                },
                'CoolingRelay2': {
                    'type': 'GPIORelay',
                    'pin': 2
                }
            }
        """
        raise NotImplementedError("get_relay_config must be implemented in subclass")

    def get_relays(self):
        # TODO: there is a bug somewhere here where gdrive isn't set up initially
        if self._relays and not self.is_config_changed():
            return self._relays
        dict_data = self.get_relay_config()
        for relay in dict_data.keys():
            self.log.debug("loading relay {}".format(relay))
            self._relays[relay] = self.objectify_dict(relay, dict_data[relay], default_type=Relay)
        return self._relays

    def get_datasource_config(self):
        """
        Returns a dictionary of datasource configurations, with the top-level keys
        being the names of each defined datasource, eg::

            {
                'BrewometerSpreadsheet': {
                    'type': 'BrewometerGoogleSheet',
                    'spreadsheet_id': '1x09d0291n31309audfa-3298193u41',
                    'client_secret_file': '/home/foo/bar/creds.json'
                }
            }

        """
        raise NotImplementedError("get_datasource_config needs to be implemented")

    def get_datasources(self):
        if self._datasources and not self.is_config_changed():
            return self._datasources
        dict_data = self.get_datasource_config()
        for objname in dict_data.keys():
            self.log.debug("loading datasource {}".format(objname))
            self._datasources[objname] = self.objectify_dict(objname, dict_data[objname])
        return self._datasources

    def get_beer_configuration(self):
        """
        Returns a dictionary of beer configuration from the datasource, eg::

            {
                'PB0044': {
                    'type': 'SetPointBeer',
                    'datasource': 'BrewometerSpreadsheet',
                    'set_point': 18.5,
                    'threshold': 0.3,
                    'data_age_warning_time': 3600
                }
            }

        """
        raise NotImplementedError("get_beer_configuration needs to be implemented")

    def get_beers(self):
        if self._beers and not self.is_config_changed():
            return self._beers
        dict_data = self.get_beer_configuration()
        for objname in dict_data.keys():
            self.log.debug("loading beer {}".format(objname))
            self._beers[objname] = self.objectify_dict(objname, dict_data[objname])
        return self._beers

    def get_manager_configuration(self):
        """
        Returns a dictionary of manager configurations, like this::

            {
                'French Saison': {
                    'beer': 'PB0044',
                    'active_cooling_relay': 'CoolingRelay1',
                    'polling_frequency': 30,
                    'active_cooling': True
                }
            }
        """
        raise NotImplementedError("get_manager_configuration needs implementation")

    def get_managers(self):
        if self._managers and not self.is_config_changed():
            return self._managers
        dict_data = self.get_manager_configuration()
        for objname in dict_data.keys():
            self.log.debug("loading manager {}".format(objname))
            self._managers[objname] = self.objectify_dict(
                objname, dict_data[objname], default_type=ManagerThread)
        return self._managers

    def objectify_dict(self, name, dict_data, default_type=None):
        "Converts a dictionary of object configuration to an object"
        klass = default_type
        if 'type' in dict_data:
            klass = str_to_class(dict_data['type'])
        if not klass:
            raise RuntimeError("no class could be found for {}".format(name))
        if issubclass(klass, ManagerThread):
            dict_data = self._vivify_config_relays(dict_data)
            dict_data = self._vivify_config_beers(dict_data)
        elif issubclass(klass, AbstractBeer):
            dict_data = self._vivify_config_datasources(dict_data)
        if dict_data['config'] == 'inherit':
            dict_data['config'] = self._config
        return klass(
            name,
            **dict_data['config']
        )

    def _vivify_config_datasources(self, dict_data):
        if 'datasource' in dict_data['config']:
            if dict_data['config']['datasource'] in self._datasources:
                dict_data['config']['datasource'] = self._datasources[
                    dict_data['config']['datasource']]
            else:
                raise RuntimeError(
                    "datasource {} is specified in beer {}, but not configured".format(
                        dict_data['config']['datasource'], name))
        return dict_data

    def _vivify_config_beers(self, dict_data):
        if 'beer' in dict_data['config']:
            if dict_data['config']['beer'] in self._beers:
                dict_data['config']['beer'] = self._beers[
                    dict_data['config']['beer']]
            else:
                raise RuntimeError(
                    "beer {} is specified in manager {}, but not configured".format(
                        dict_data['config']['beer'], name))
        return dict_data

    def _vivify_config_relays(self, dict_data):
        if 'active_cooling_relay' in dict_data['config']:
            if dict_data['config']['active_cooling_relay'] in self._relays:
                dict_data['config']['active_cooling_relay'] = self._relays[
                    dict_data['config']['active_cooling_relay']]
            else:
                raise RuntimeError(
                    "active_cooling_relay {} is specified in manager {}, but not configured".format(
                        dict_data['config']['active_cooling_relay'], name))
        if 'active_heating_relay' in dict_data['config']:
            if dict_data['config']['active_heating_relay'] in self._relays:
                dict_data['config']['active_heating_relay'] = self._relays[
                    dict_data['config']['active_heating_relay']]
            else:
                raise RuntimeError(
                    "active_heating_relay {} is specified in manager {}, but not configured".format(
                        dict_data['config']['active_heating_relay'], name))
        return dict_data

class GoogleSheetConfig(FermenatorConfig):
    """
    This class implements configuration as a google sheet. Sheet data
    is read and classes are assembled for Managers, Beers, DataSources
    and Relays.

    You must provide 'spreadsheet_id' as a kwarg to this class.
    """

    def __init__(self, name, **kwargs):
        super(self.__class__, self).__init__(self, name, **kwargs)
        if not 'spreadsheet_id' in kwargs:
            raise RuntimeError("no configuration spreadsheet id provided")
        self._gs = GoogleSheet("{}-spreadsheet".format(name), **kwargs)

    def is_config_changed(self):
        return self._gs._is_spreadsheet_changed()

    def get_relay_config(self):
        return sheet_data_to_dict(self.get_sheet_range_values(
            range='Relay!A2:C'))

    def get_datasource_config(self):
        return sheet_data_to_dict(self.get_sheet_range_values(
            range='DataSource!A2:C'))

    def get_beer_configuration(self):
        return sheet_data_to_dict(self.get_sheet_range_values(
            range='Beer!A2:C'))

    def get_manager_configuration(self):
        return sheet_data_to_dict(self.get_sheet_range_values(
            range='Manager!A2:C'))

class FirebaseConfig(FermenatorConfig):

    #: A prefix under which all configuration values should be found
    PREFIX = ('config', 'fermenator')

    def __init__(self, name, **kwargs):
        """
        As with :class:`FirebaseDataSource`, pass in a kwarg dictionary with
        required keys to connect to a firebase database. By default, this class
        will look at the path /config/fermenator for configuration specific to
        this app.
        """
        super(self.__class__, self).__init__(name, **kwargs)
        self._fb = FirebaseDataSource("{}-db".format(name), **kwargs)
        self._version = self.upstream_version()

    def upstream_version(self):
        "Returns the current configuration version"
        return self._fb.get(self.PREFIX + ('version',))

    def is_config_changed(self):
        if self._version == self.upstream_version():
            return False
        return True

    def get_relay_config(self):
        data = self._fb.get(self.PREFIX + ('relays',))
        if data:
            return data
        return {}

    def get_datasource_config(self):
        data = self._fb.get(self.PREFIX + ('datasources',))
        if data:
            return data
        return {}

    def get_beer_configuration(self):
        data = self._fb.get(self.PREFIX + ('beers',))
        if data:
            return data
        return {}

    def get_manager_configuration(self):
        data = self._fb.get(self.PREFIX + ('managers',))
        if data:
            return data
        return {}

    def import_yaml_file(self, filename):
        self.log.info("importing config from {}".format(filename))
        import yaml
        with open(filename) as confyaml:
            cdata = yaml.load(confyaml)
        handle = self._fb._fb_hndl
        for path in self.PREFIX:
            handle = handle.child(path)
        handle.set(cdata)
