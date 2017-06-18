from oauth2client.service_account import ServiceAccountCredentials
import httplib2
from apiclient import discovery
import logging

import fermenator.datasource

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
    def __init__(self, config=None):
        """
        Config must consist of a dictionary with at least the following
        keys:

        - client_secret: a path to a json file containing the client secret key
        """
        self.log = logging.getLogger(
            "{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__))
        self._config = config
        self._google_credentials = None
        self._ss_service_handle = None
        self._ss_cache = {}
        self._ss_cache_tokens = {}
        self._drive_service_handle = None
        self._scopes = (
            'https://www.googleapis.com/auth/spreadsheets.readonly',
            'https://www.googleapis.com/auth/drive.readonly')

    def get(self, key):
        pass

    def set(self, key):
        raise NotImplementedError(
            "Setting keys in google sheets is not supported")

    def get_sheet_range(self, spreadsheet_id, range=None):
        """
        Retreive a range for the given spreadsheet ID. Range data will be cached locally
        to avoid re-getting the same data over and over again through the API. Any
        changes to a spreadsheet will cause the cache to be invalidated and new sheet
        data to be retrieved.

        `range` should follow the same convention as a linked cell, for example::

            Sheet1!A1:E

        """
        cache_key = "%s-%s" % (spreadsheet_id, range)
        if not cache_key in self._ss_cache or self._is_spreadsheet_changed(spreadsheet_id):
            self.log.debug("getting new sheet data")
            self._ss_cache[cache_key] = self._ss_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range).execute()
        return self._ss_cache[cache_key]

    def get_sheet_range_values(self, spreadsheet_id, range=None):
        """
        Same as :meth:`get_sheet_range` except that this function returns only
        values for that range rather than other metadata such as formulae.
        """
        return self.get_sheet_range(spreadsheet_id, range).get('values', [])

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
        if self._google_credentials is None:
            self.log.debug("getting new google service credentials")
            try:
                self._google_credentials = ServiceAccountCredentials.from_json_keyfile_name(
                    self._config['client_secret'], self._scopes)
            except KeyError:
                raise RuntimeError("No client_secret path found in config")
            except TypeError:
                raise RuntimeError("config does not appear to be a dictionary")
        return self._google_credentials

    def _get_ss_service(self):
        """
        Uses the google oauth API to get a valid set of temporary credentials
        that will be used for spreadsheets access.
        """
        self.log.debug("getting new spreadsheet service handle")
        self._ss_service_handle = discovery.build(
            'sheets', 'v4', http=self._credentials.authorize(httplib2.Http()),
            discoveryServiceUrl='https://sheets.googleapis.com/$discovery/rest?version=v4',
            cache_discovery=False)

    def _get_drive_service(self):
        """
        Uses the google oauth API to get a valid set of temporary credentials
        that will be used for google drive access. Drive is used to detect changes
        in the spreadsheet data such that a full download of sheet data only occurs
        whenever the sheet is changed; the rest of the time cached data is used.
        """
        self.log.debug("getting new drive service handle")
        self._drive_service_handle = discovery.build(
            'drive', 'v3', http=self._credentials.authorize(httplib2.Http()),
            cache_discovery=False)

    def _is_spreadsheet_changed(self, spreadsheet_id):
        """
        Checks the drive API for changes to the specified spreadsheet (file), caches
        state so that subsequent calls to this method only return new changes since the
        last call. Supports tracking changes across multiple spreadsheets.
        """
        have_change = False
        page_token = None
        if not spreadsheet_id in self._ss_cache_tokens:
            self.log.debug("initializing spreadsheet pageToken cache for {}".format(spreadsheet_id))
            self._ss_cache_tokens[spreadsheet_id] = self._drive_service.changes().getStartPageToken().execute()['startPageToken']
        page_token = self._ss_cache_tokens[spreadsheet_id]
        while page_token is not None:
            response = self._drive_service.changes().list(pageToken=page_token,
                                                    spaces='drive').execute()
            for change in response.get('changes'):
                # Process change
                if change.get('fileId') == spreadsheet_id:
                    self.log.debug("matching change found in file {}".format(change.get('fileId')))
                    have_change = True
                else:
                    self.log.debug("ignoring change found in unmatched file {}".format(change.get('fileId')))
            if 'newStartPageToken' in response:
                # Last page, save this token for the next polling interval
                self._ss_cache_tokens[spreadsheet_id] = response.get('newStartPageToken')
            page_token = response.get('nextPageToken')
        return have_change


class BrewometerGoogleSheet(GoogleSheet):

    def get(self, key):
        """
        Key should consist of the batch id.
        Values returned will be an iterable in reverse time order consisting of
        dictionary fields for `timestamp`, `batch_id`, `colour`, `temperature`,
        and `gravity`.
        """
        pass
