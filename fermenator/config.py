"""
The classes in this module deal with the loading of configuration as well as
the actual running of the software, because all classes descending from
:class:`FermenatorConfig` are in charge of reading the configuration from some
datastore, rendering it into objects, and starting monitoring for each beer
object in a separate thread.
"""
import logging
import gc
import sys
import os.path
import time
from yaml import load as load_yaml

from .datasource.gsheet import GoogleSheet, BrewometerGoogleSheet
from .datasource.firebase import (
    FirebaseDataSource, BrewConsoleFirebaseDS)
from .datasource.carbon import CarbonDataSource
from .statelogger import StateLogger
from .relay import Relay, GPIORelay, MCP23017Relay
from .beer import AbstractBeer, SetPointBeer, LinearBeer
from .manager import ManagerThread
from .exception import (
    ConfigurationError, ClassNotFoundError, ConfigNotFoundError)

def bootstrap():
    """
    Returns a fully configured :class:`FermenatorConfig` object or one of its
    descendants based on bootstrap configuration.
    """
    config = load_bootstrap_configuration()
    config_klass = get_class_by_name(config['bootstrap']['type'])
    return config_klass(config['bootstrap']['name'], **config['bootstrap']['config'])

def get_class_by_name(name):
    "Returns a configuration class by name (not an instance)"
    if name in ('DictionaryConfig', 'GoogleSheetConfig', 'FirebaseConfig'):
        return globals()[name]
    raise ClassNotFoundError("no configuration class {} could be found".format(name))

def str_to_class(classname):
    "Returns a reference to any class in the current scope"
    try:
        return getattr(sys.modules[__name__], classname)
    except NameError:
        raise ClassNotFoundError(
            "no class {} was found in the current scope".format(
                classname
            ))

def garbage_collect():
    """
    Run a two-pass garbage collection
    """
    logging.getLogger("{}.garbage_collect".format(__name__)).debug("collecting")
    for _ in range(2):
        gc.collect()

def sheet_data_to_dict(sheet_data):
    """
    Convert data retrieved from a configuration-style spreadsheet to a dict
    """
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

#: A tuple of default bootstrap configuration file locations
BOOTSTRAP_CONFIG_FILES = (
    '.fermenator', '~/.fermenator/config', '/etc/fermenator/config'
)

def load_bootstrap_configuration():
    """
    Look for YaML configuration in local files, using the first file found,
    in the following order:

    - Locally provided config_file (from kwargs)
    - .fermenator (local directory)
    - ~/.fermenator/config (home directory)
    - /etc/fermenator/config (system configuration directory)

    Once config is found, parse it into a dictionary and return it
    """
    for location in BOOTSTRAP_CONFIG_FILES:
        try:
            with open(os.path.expanduser(location)) as yfile:
                return load_yaml(yfile)
        except (FileNotFoundError, IsADirectoryError):
            continue
    raise ConfigNotFoundError("No configuration could be found/loaded")

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
        for name, obj in self._managers.items():
            obj.stop()
            obj.join(30.0)
            if obj.isAlive():
                self.log.error("manager thread %s could not be stopped", name)
        self._managers = dict()
        self._beers = dict()
        self._datasources = dict()
        self._relays = dict()
        garbage_collect()

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
                for _, obj in self._managers.items():
                    obj.start()
                fresh = True
                while fresh:
                    time.sleep(self.refresh_interval)
                    if not self.stop and self.is_config_changed():
                        self.log.info("detected new configuration data")
                        fresh = False
                self.disassemble()
        except KeyboardInterrupt:
            self.disassemble()

    def is_config_changed(self):
        """
        Returns True if configuration has changed. Must be implemented in a
        subclass.
        """
        raise NotImplementedError(
            "is_config_changed needs to be implemented in subclass")

    def get_relay_config(self):
        """
        Returns a dictionary containing a list of relays and their config
        values, eg::

            {
                'CoolingRelay1': {
                    'type': 'GPIORelay',
                    'config': {
                        'gpio_pin': 1
                    }
                },
                'CoolingRelay2': {
                    'type': 'GPIORelay',
                    'config': {
                        'gpio_pin': 2,
                        'duty_cycle': 0.5,
                        'cycle_time': 600
                    }
                }
            }
        """
        raise NotImplementedError("get_relay_config must be implemented in subclass")

    def get_relays(self):
        """
        Assembles and returns a dictionary of relay objects based on
        configuration data. Caches the results locally, and will rebuild the
        dictionary if configuration changes are detected.
        """
        if self._relays and not self.is_config_changed():
            return self._relays
        dict_data = self.get_relay_config()
        for name in dict_data:
            self.log.debug("loading relay %s", name)
            self._relays[name] = self.objectify_dict(name, dict_data[name], default_type=Relay)
        return self._relays

    def get_datasource_config(self):
        """
        Returns a dictionary of datasource configurations, with the top-level keys
        being the names of each defined datasource, eg::

            {
                'BrewometerSpreadsheet': {
                    'type': 'BrewometerGoogleSheet',
                    'config': {
                        'spreadsheet_id': '1x09d0291n31309audfa-3298193u41',
                        'client_secret_file': '/home/foo/bar/creds.json'
                    }
                }
            }

        """
        raise NotImplementedError("get_datasource_config needs to be implemented")

    def get_datasources(self):
        """
        Assembles and returns a dictionary of datasource objects based on
        configuration data. Caches the results locally, and will rebuild the
        dictionary if configuration changes are detected.
        """
        if self._datasources and not self.is_config_changed():
            return self._datasources
        dict_data = self.get_datasource_config()
        for name in dict_data:
            self.log.debug("loading datasource %s", name)
            self._datasources[name] = self.objectify_dict(name, dict_data[name])
        return self._datasources

    def get_beer_configuration(self):
        """
        Returns a dictionary of beer configuration from the datasource, eg::

            {
                'PB0044': {
                    'type': 'SetPointBeer',
                    'config': {
                        'datasource': 'BrewometerSpreadsheet',
                        'set_point': 18.5,
                        'threshold': 0.3,
                        'data_age_warning_time': 3600
                    }
                }
            }

        """
        raise NotImplementedError("get_beer_configuration needs to be implemented")

    def get_beers(self):
        """
        Assembles and returns a dictionary of beer objects based on
        configuration data. Caches the results locally, and will rebuild the
        dictionary if configuration changes are detected.
        """
        if self._beers and not self.is_config_changed():
            return self._beers
        dict_data = self.get_beer_configuration()
        for objname in dict_data:
            self.log.debug("loading beer %s", objname)
            self._beers[objname] = self.objectify_dict(objname, dict_data[objname])
        return self._beers

    def get_manager_configuration(self):
        """
        Returns a dictionary of manager configurations, like this::

            {
                'French Saison': {
                    'config': {
                        'beer': 'PB0044',
                        'active_cooling_relay': 'CoolingRelay1',
                        'polling_frequency': 30,
                        'active_cooling': True
                    }
                }
            }
        """
        raise NotImplementedError("get_manager_configuration needs implementation")

    def get_managers(self):
        """
        Assembles and returns a dictionary of manager objects based on
        configuration data. Caches the results locally, and will rebuild the
        dictionary if configuration changes are detected.
        """
        if self._managers and not self.is_config_changed():
            return self._managers
        dict_data = self.get_manager_configuration()
        for objname in dict_data:
            self.log.debug("loading manager %s", objname)
            self._managers[objname] = self.objectify_dict(
                objname, dict_data[objname], default_type=ManagerThread)
        return self._managers

    def objectify_dict(self, name, dict_data, default_type=None):
        "Converts a dictionary of object configuration to an object"
        klass = default_type
        if 'type' in dict_data:
            klass = str_to_class(dict_data['type'])
        if issubclass(klass, ManagerThread):
            dict_data = self._vivify_config_relays(dict_data)
            dict_data = self._vivify_config_beers(dict_data)
            dict_data = self._vivify_config_state_logger_ds(dict_data)
        elif issubclass(klass, AbstractBeer):
            dict_data = self._vivify_config_datasources(dict_data)
        if dict_data['config'] == 'inherit':
            dict_data['config'] = self._config
        return klass(
            name,
            **dict_data['config']
        )

    def _vivify_config_datasources(self, dict_data):
        """
        Pass this method class configuration data (as would be provided to
        **kwargs when vivifying a class), and it will search for any
        specified datasources, replacing textual links with a true object
        representing that datasource. Not safe to run twice on the same data.
        """
        try:
            dict_data['config']['datasource'] = self._datasources[
                dict_data['config']['datasource']]
        except KeyError:
            raise ConfigurationError(
                "error in datasource configuration for beer")
        return dict_data

    def _vivify_config_state_logger_ds(self, dict_data):
        """
        Pass this method class configuration data (as would be provided to
        **kwargs when vivifying a class), and it will search for any
        specified state logger datasources, replacing textual links with a true
        object representing that datasource. Not safe to run twice on the same
        data.
        """
        try:
            state_loggers = dict_data['config']['state_loggers']
        except KeyError:
            return dict_data
        for name in state_loggers:
            logger_config = state_loggers[name]['config']
            try:
                logger_config['datasource'] = \
                    self._datasources[logger_config['datasource']]
            except KeyError:
                raise ConfigurationError(
                    "state_logger {} defined without datasource".format(name))
            dict_data['config']['state_loggers'][name] = StateLogger(
                name, **logger_config)
        return dict_data

    def _vivify_config_beers(self, dict_data):
        """
        Pass this method class configuration data (as would be provided to
        **kwargs when vivifying a class), and it will search for any
        specified beers, replacing textual links with a true object
        representing that beer. Not safe to run twice on the same data.
        """
        try:
            dict_data['config']['beer'] = self._beers[
                dict_data['config']['beer']]
        except KeyError:
            raise ConfigurationError(
                "error in manager configuration related to beer")
        return dict_data

    def _vivify_config_relays(self, dict_data):
        """
        Pass this method class configuration data (as would be provided to
        **kwargs when vivifying a class), and it will search for any
        specified relays, replacing textual links with a true object
        representing that relay. Not safe to run twice on the same data.
        """
        if 'active_cooling_relay' in dict_data['config']:
            try:
                dict_data['config']['active_cooling_relay'] = self._relays[
                    dict_data['config']['active_cooling_relay']]
            except KeyError:
                raise ConfigurationError("error in active_cooling_relay config")
        if 'active_heating_relay' in dict_data['config']:
            try:
                dict_data['config']['active_heating_relay'] = self._relays[
                    dict_data['config']['active_heating_relay']]
            except KeyError:
                raise ConfigurationError("error in active_heating_relay config")
        return dict_data

class DictionaryConfig(FermenatorConfig):
    """
    Directly provide a dictionary of configuration to this class. Object references
    should be in the text form rather than class instances. Essentially, this class
    is designed to be passed config read out of a yaml or json file, or passed
    directly from testing code.

    When instantiating this config, you should directly pass the top-level config
    dictionary as kwargs, eg::

        config_dict = yaml.load(configfile)
        config_obj = DictionaryConfig('somename', **config_dict)

    """

    def get_relay_config(self):
        "Returns the `relays` section of the dictionary config"
        return self._config['relays']

    def get_datasource_config(self):
        "Returns the `datasources` section of the dictionary config"
        return self._config['datasources']

    def get_beer_configuration(self):
        "Returns the `beers` section of the dictionary config"
        return self._config['beers']

    def get_manager_configuration(self):
        "Returns the `managers` section of the dictionary config"
        return self._config['managers']

    def is_config_changed(self):
        "Returns False always because config is loaded once from the file"
        return False

class GoogleSheetConfig(FermenatorConfig):
    """
    This class implements configuration as a google sheet. Sheet data
    is read and classes are assembled for Managers, Beers, DataSources
    and Relays.

    You must provide 'spreadsheet_id' as a kwarg to this class.
    """

    def __init__(self, name, **kwargs):
        """
        Provide a spreadsheet_id as kwarg to this class, as well as any kwargs
        supported by the parent class.
        """
        super(GoogleSheetConfig, self).__init__(self, name, **kwargs)
        if 'spreadsheet_id' not in kwargs:
            raise ConfigurationError("no configuration spreadsheet id provided")
        self._gs = GoogleSheet("{}-spreadsheet".format(name), **kwargs)

    def is_config_changed(self):
        """
        Checks the google drive api to determine if the underlying spreadsheet
        content has changed, returns True if it has.
        """
        return self._gs.is_spreadsheet_changed()

    def get_relay_config(self):
        """
        Retreives the Relay information from the underlying spreadsheet.
        """
        return sheet_data_to_dict(self._gs.get_sheet_range_values(
            range='Relay!A2:C'))

    def get_datasource_config(self):
        """
        Retreives the Datasource information from the underlying spreadsheet.
        """
        return sheet_data_to_dict(self._gs.get_sheet_range_values(
            range='DataSource!A2:C'))

    def get_beer_configuration(self):
        """
        Retreives the Beer information from the underlying spreadsheet.
        """
        return sheet_data_to_dict(self._gs.get_sheet_range_values(
            range='Beer!A2:C'))

    def get_manager_configuration(self):
        """
        Retreives the Manager information from the underlying spreadsheet.
        """
        return sheet_data_to_dict(self._gs.get_sheet_range_values(
            range='Manager!A2:C'))

class FirebaseConfig(FermenatorConfig):
    """
    Read configuration data from a Firebase datastore and assemble an operating
    environment.
    """

    #: A prefix under which all configuration values should be found
    PREFIX = ('config', 'fermenator')

    def __init__(self, name, **kwargs):
        """
        As with :class:`FirebaseDataSource`, pass in a kwarg dictionary with
        required keys to connect to a firebase database. By default, this class
        will look at the path /config/fermenator for configuration specific to
        this app.
        """
        super(FirebaseConfig, self).__init__(name, **kwargs)
        self._fb = FirebaseDataSource("{}-db".format(name), **kwargs)
        self._version = None

    def upstream_version(self):
        "Returns the current configuration version"
        return self._fb.get(self.PREFIX + ('version',))

    def is_config_changed(self):
        """
        Checks the version key in the configuration store and returns True if
        the version has changed since config was last loaded
        """
        upstream_version = self.upstream_version()
        if self._version == upstream_version:
            return False
        return True

    def get_relay_config(self):
        """
        Retrieve relay configuration from the datastore
        """
        data = self._fb.get(self.PREFIX + ('relays',))
        if data:
            return data
        return {}

    def get_datasource_config(self):
        """
        Retrieve datasource configuration from the datastore
        """
        data = self._fb.get(self.PREFIX + ('datasources',))
        if data:
            return data
        return {}

    def get_beer_configuration(self):
        """
        Retrieve beer configuration from the datastore
        """
        data = self._fb.get(self.PREFIX + ('beers',))
        if data:
            return data
        return {}

    def get_manager_configuration(self):
        """
        Retrieve manager configuration from the datastore
        """
        data = self._fb.get(self.PREFIX + ('managers',))
        if data:
            return data
        return {}

    def import_yaml_file(self, filename):
        """
        Import dictionary config data from a YaML file.
        """
        self.log.info("importing config from %s", filename)
        import yaml
        with open(filename) as confyaml:
            cdata = yaml.load(confyaml)
        handle = self._fb._fb_hndl
        for path in self.PREFIX:
            handle = handle.child(path)
        handle.set(cdata)

    def assemble(self):
        self._version = self.upstream_version()
        self.log.info("assembling with version %s", self._version)
        super(FirebaseConfig, self).assemble()
