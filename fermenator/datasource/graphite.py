"""
This module contains the datasource for reading temperature and gravity data
out of carbon/graphite.
"""
import requests
from . import DataSource
from fermenator.exception import DataFetchError, ConfigurationError

class GraphiteDataSource(DataSource):
    """
    A graphite data source. This class only implements get operations,
    since set type operations must be made against a totally different API
    (carbon).
    """

    def __init__(self, name, **kwargs):
        """
        Provide this method with the following:

        - url (the base url to graphite)
        - user (optional, password is required if user is used)
        - password (optional)
        """
        super(GraphiteDataSource, self).__init__(name, **kwargs)
        if 'url' not in kwargs:
            raise ConfigurationError("url must be provided in kwargs")
        else:
            self.url = kwargs['url'].rstrip('/')
        self._config = kwargs
        if 'user' in kwargs and 'password' in kwargs:
            self.auth = (kwargs['user'].strip(), kwargs['password'].strip())
        else:
            self.auth = None

    def get(self, key):
        """
        Given a hierarchical key name in the form of an iterable, return a
        handle to the dataset found at the key.
        """
        url = self._build_url(key, 60*5)
        result = requests.get(url, auth=self.auth)
        try:
            raw_results = result.json()[0]['datapoints']
            raw_results.reverse()
            for row in raw_results:
                yield row
        except IndexError:
            raise DataFetchError(
                "tried to read data that doesn't exist at {}".format(
                    '.'.join(key)
            ))

    def _build_url(self, target, time_limit_s):
        """
        Construct a URL to retrieve the data at target, where target is
        an iterable list of keys decending into the heirarchy.
        """
        return "{}/render?target={}&from=-{}s&format=json".format(
            self.url, '.'.join(target), time_limit_s
        )
