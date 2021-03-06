"""
This class includes the objects that expose google sheet data as either
configuration or beer information.
"""
import logging
from collections import deque
import re
from oauth2client.service_account import ServiceAccountCredentials
import requests
from apiclient import discovery

import fermenator.datasource
from fermenator.exception import ConfigurationError, DataFetchError
from fermenator.conversions import temp_f_to_c, sg_to_plato, convert_spreadsheet_date

DEFAULT_CREDENTIAL_LOCATIONS = (
    '.credentials.json',
    '~/.fermenator/credentials.json',
    '/etc/fermenator/credentials.json')

class GoogleSheet(fermenator.datasource.DataSource):
    """
    A base class designed to allow a user to get data from a google sheets
    document. This class handles the authentication to the sheets API, but
    does not directly implement getters and setters for the sheets. Subclasses
    should be created for various spreadsheet formats to make getting and setting
    of data easy and performant based on the type of fetches required.

    All gsheet interactions require OAUTH with a client credential file. This
    code is based on the concepts found here:

    https://developers.google.com/sheets/api/quickstart/python
    """
    def __init__(self, name, **kwargs):
        """
        This object requires one kwarg, spreadsheet_id.
        """
        super(GoogleSheet, self).__init__(name, **kwargs)
        self.name = name
        try:
            self._ss_id = kwargs['spreadsheet_id']
        except KeyError:
            raise ConfigurationError("spreadsheet_id must be provided")
        #self.log.debug("config: {}".format(self._config))
        self._google_credentials = None
        self._ss_service_handle = None
        self._ss_cache = dict()
        self._ss_cache_tokens = dict()
        self._drive_service_handle = None
        self._has_refreshed = False
        self._scopes = (
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly')

    def get(self, key):
        """
        This function is the one used to retrieve spreadsheet data, it must be
        implemented in a child class for the specific sheet.
        """
        raise NotImplementedError(
            "Getting keys in google sheets is not supported")

    def set(self, key, value):
        """
        This function is the one used to set spreadsheet data, it must be
        implemented in a child class for the specific sheet.
        """
        raise NotImplementedError(
            "Setting keys in google sheets is not supported")

    def get_sheet_range(self, range=None):
        """
        Retreive a range for the given spreadsheet ID. Range data will be cached locally
        to avoid re-getting the same data over and over again through the API. Any
        changes to a spreadsheet will cause the cache to be invalidated and new sheet
        data to be retrieved.

        `range` should follow the same convention as a linked cell, for example::

            Sheet1!A1:E

        """
        cache_key = "%s" % (range,)
        if not cache_key in self._ss_cache or self.is_spreadsheet_changed():
            self.log.debug("getting new sheet data for range %s", range)
            self._ss_cache[cache_key] = self._ss_service.spreadsheets().values().get(
                spreadsheetId=self._ss_id,
                range=range).execute()
            self._has_refreshed = True
        return self._ss_cache[cache_key]

    def is_refreshed(self):
        """
        Returns true if data has refreshed since the last time this was checked.
        """
        #self.log.debug("checking freshness for sheet {}".format(spreadsheet_id))
        if self._has_refreshed:
            self._has_refreshed = False
            return True
        return False

    def get_sheet_range_values(self, range=None):
        """
        Same as :meth:`get_sheet_range` except that this function returns only
        values for that range rather than other metadata such as formulae.
        """
        return self.get_sheet_range(range).get('values', [])

    @property
    def _ss_service(self):
        "Returns the gsheet service object"
        if self._ss_service_handle is None:
            self.log.debug('initializing spreadsheet service')
            self._get_ss_service()
        return self._ss_service_handle

    @property
    def _drive_service(self):
        "Returns the drive service object"
        if self._drive_service_handle is None:
            self.log.debug('initializing drive service')
            self._get_drive_service()
        return self._drive_service_handle

    @property
    def _credentials(self):
        """
        Returns the google credential object based on the json credential
        keyfile.
        """
        if self._google_credentials is None:
            self.log.debug("getting new google service credentials")
            try:
                self._google_credentials = ServiceAccountCredentials.from_json_keyfile_name(
                    self._get_credential_config(), self._scopes)
            except KeyError:
                raise ConfigurationError("No client_secret path found in config")
            except TypeError:
                raise ConfigurationError("config does not appear to be a dictionary")
        return self._google_credentials

    def _get_credential_config(self):
        """
        This method attempts to find a json credential key file at one of the
        :attr:`DEFAULT_CREDENTIAL_LOCATIONS`.
        """
        if 'client_secret_file' in self._config:
            return self._config['client_secret_file']
        import os.path
        for location in DEFAULT_CREDENTIAL_LOCATIONS:
            if os.path.exists(os.path.expanduser(location)):
                return os.path.expanduser(location)
        raise ConfigurationError("no configuration found for client secret file")

    def _get_ss_service(self):
        """
        Uses oauth2 credentials from :meth:`_credentials` to gain a handle to the
        google sheets API.
        """
        self.log.debug("getting new spreadsheet service handle")
        self._ss_service_handle = discovery.build(
            'sheets', 'v4', http=self._credentials.authorize(CustomHttp()),
            discoveryServiceUrl='https://sheets.googleapis.com/$discovery/rest?version=v4',
            cache_discovery=False)

    def _get_drive_service(self):
        """
        Uses temporary oauth2 credentils to gain a handle to the google drive API.
        Drive is used to detect changes in the spreadsheet data such that a full
        download of sheet data only occurs whenever the sheet is changed; the rest
        of the time cached data is used.
        """
        self.log.debug("getting new drive service handle")
        self._drive_service_handle = discovery.build(
            'drive', 'v3', http=self._credentials.authorize(CustomHttp()),
            cache_discovery=False)

    def is_spreadsheet_changed(self):
        """
        Checks the drive API for changes to the specified spreadsheet (file), caches
        state so that subsequent calls to this method only return new changes since the
        last call. Supports tracking changes across multiple spreadsheets.
        """
        have_change = False
        page_token = None
        if not self._ss_id in self._ss_cache_tokens:
            self.log.debug("initializing spreadsheet pageToken cache")
            self._ss_cache_tokens[self._ss_id] = self._drive_service.changes().getStartPageToken().execute()['startPageToken']
        page_token = self._ss_cache_tokens[self._ss_id]
        while page_token is not None:
            response = self._drive_service.changes().list(pageToken=page_token,
                                                          spaces='drive').execute()
            for change in response.get('changes'):
                # Process change
                if change.get('fileId') == self._ss_id:
                    self.log.debug("matching change found in file %s", change.get('fileId'))
                    have_change = True
                else:
                    self.log.debug("ignoring change found in unmatched file %s", change.get('fileId'))
            if 'newStartPageToken' in response:
                # Last page, save this token for the next polling interval
                self._ss_cache_tokens[self._ss_id] = response.get('newStartPageToken')
            page_token = response.get('nextPageToken')
        return have_change


class BrewometerGoogleSheet(GoogleSheet):
    """
    This class is designed to read data out of a spreadsheet created by the
    brewometer (Tilt) manufacturer, where the data is appended to a worksheet
    called ``Sheet1``.
    """

    def __init__(self, name, **kwargs):
        """
        Pass a spreadsheet_id as a key in the config dictionary.
        """
        super(BrewometerGoogleSheet, self).__init__(name, **kwargs)
        self._data = dict()
        self._temperature_unit = 'C'
        self.gravity_unit = 'P'
        self.batch_id_regex = r'\w+'

    @property
    def temperature_unit(self):
        """
        Returns the current temperature unit
        """
        return self._temperature_unit

    @temperature_unit.setter
    def temperature_unit(self, value):
        """
        Sets the current temperature unit.
        """
        unit = value.upper()
        if not unit in ('C', 'F'):
            raise ConfigurationError("Temperature unit must be either 'C' or 'F'")
        self._temperature_unit = unit

    def _formatted_data(self):
        """
        This method wraps the :meth:`get_sheet_range_values` method,
        specifying the spreadsheet id and range. The called method
        caches the data locally but will grab new data whenever it is
        present. Further, the method sorts the data into a dictionary
        that supports key-based access.
        """
        raw_data = self.get_sheet_range_values(range='Sheet1!A2:E')
        if self.is_refreshed():
            self.log.debug("data refreshed, building data structure")
            for row in raw_data:
                try:
                    try:
                        beername = row[4].upper().strip()
                    except IndexError:
                        continue
                    batch_id_match = re.match(self.batch_id_regex, beername)
                    if batch_id_match:
                        beername = batch_id_match.group(0)
                    temp = float(row[2])
                    if self.temperature_unit == 'C':
                        temp = temp_f_to_c(temp)
                    gravity = float(row[1])
                    if self.gravity_unit.upper() == 'P':
                        gravity = sg_to_plato(gravity)
                    structured = {
                        'batch_id': beername,
                        'timestamp': convert_spreadsheet_date(row[0]),
                        'gravity': gravity,
                        'temperature': temp,
                        'tilt_color': row[3]
                    }
                    if beername in self._data:
                        self._data[beername].appendleft(structured)
                    else:
                        self._data[beername] = deque(
                            [structured])
                except IndexError:
                    self.log.error("error in row: %s", row)
        return self._data

    def get(self, key):
        """
        Key should consist of the batch id, as the first item in an interable,
        such as a list, tuple, or deque. Don't pass in a bare string.

        Values returned will be an iterable in reverse time order consisting of
        dictionary fields for `timestamp`, `tilt_color`, `temperature`,
        and `gravity`.
        """
        pri_key = key[0].upper()
        if pri_key in self._formatted_data():
            for row in self._formatted_data()[pri_key]:
                if len(key) > 1:
                    if key[1].lower() in row:
                        yield {
                            'timestamp': row['timestamp'],
                            key[1].lower(): row[key[1].lower()]}
                    else:
                        raise DataFetchError(
                            "key {} specified but not found in data".format(
                                key))
                else:
                    yield row
        else:
            self.log.warning(
                "request for batch id %s, but that name is not found in spreadsheet",
                key)

class CustomHttp(object):
    """
    This class acts as a workaround for threading issues in Httlib2
    that cause the GoogleSheet classes above to blow up when used in
    thread context (in parallel). This class replaces the httplib2
    Http() object with an object of the same methods but using
    the requests library instead (which is threadsafe).

    This class was written by github user sadovnychyi:
    https://github.com/sadovnychyi

    Issue and code discussed here:
    https://github.com/GoogleCloudPlatform/google-cloud-python/issues/1214

    """
    def __init__(self, timeout=None):
        "Initialize the class with a configurable timeout"
        self.timeout = timeout

    def request(self, uri, method='GET', body=None, headers=None,
                redirections=None, connection_type=None):
        """
        Implement an http2lib-style request function in the requests library
        to avoid issues with thread safety.
        """
        if connection_type is not None:
            uri = '%s://%s' % (connection_type, uri)
        resp = requests.request(method=method, url=uri, data=body, headers=headers,
                                timeout=self.timeout)
        resp.status = resp.status_code
        return resp, resp.content
