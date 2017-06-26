import sys
import time
from fermenator.datasource.gsheet import *
from fermenator.relay import *
from fermenator.beer import *
from fermenator.manager import *

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

class GoogleSheetConfig(GoogleSheet):
    """
    This class implements configuration as a google sheet. Sheet data
    is read and classes are assembled for Managers, Beers, DataSources
    and Relays.
    """

    def __init__(self, name, **kwargs):
        if not 'config_spreadsheet_id' in kwargs:
            raise RuntimeError("no configuration spreadsheet id provided")
        super(GoogleSheetConfig, self).__init__(name, **kwargs)
        if 'refresh_interval' in kwargs:
            self.refresh_interval = float(kwargs['refresh_interval'])
        else:
            self.refresh_interval = 60.0
        self._relays = dict()
        self._beers = dict()
        self._managers = dict()
        self._datasources = dict()
        self.stop = False

    def assemble(self):
        """
        Reads all the configuration and assembles objects in the correct order.
        """
        self.get_relays()
        self.get_datasources()
        self.get_beers()
        self.get_managers()

    def disassemble(self):
        """
        Shuts down any running manager threads and destroys objects in the
        reverse order of creation.
        """
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
                for manager in self._managers:
                    self._managers[manager].start()
                fresh = True
                while fresh:
                    time.sleep(self.refresh_interval)
                    if not self.stop and self._is_spreadsheet_changed(self._config['config_spreadsheet_id']):
                        self.log.info("detected new configuration data")
                        fresh = False
                self.disassemble()
        except KeyboardInterrupt:
            self.disassemble()

    def get_relays(self):
        # TODO: there is a bug somewhere here where gdrive isn't set up initially
        if self._relays and not self.is_refreshed(
            self._config['config_spreadsheet_id']):
            return self._relays
        dict_data = sheet_data_to_dict(self.get_sheet_range_values(
            self._config['config_spreadsheet_id'],
            range='Relay!A2:C'))
        for relay in dict_data.keys():
            self._relays[relay] = self.objectify_dict(relay, dict_data[relay], default_type=Relay)
        return self._relays

    def get_datasources(self):
        if self._datasources and not self.is_refreshed(
            self._config['config_spreadsheet_id']):
            return self._datasources
        dict_data = sheet_data_to_dict(self.get_sheet_range_values(
            self._config['config_spreadsheet_id'],
            range='DataSource!A2:C'))
        for objname in dict_data.keys():
            self._datasources[objname] = self.objectify_dict(objname, dict_data[objname])
        return self._datasources

    def get_beers(self):
        if self._beers and not self.is_refreshed(
            self._config['config_spreadsheet_id']):
            return self._beers
        dict_data = sheet_data_to_dict(self.get_sheet_range_values(
            self._config['config_spreadsheet_id'],
            range='Beer!A2:C'))
        for objname in dict_data.keys():
            self._beers[objname] = self.objectify_dict(objname, dict_data[objname])
        return self._beers

    def get_managers(self):
        if self._managers and not self.is_refreshed(
            self._config['config_spreadsheet_id']):
            return self._managers
        dict_data = sheet_data_to_dict(self.get_sheet_range_values(
            self._config['config_spreadsheet_id'],
            range='Manager!A2:C'))
        for objname in dict_data.keys():
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
