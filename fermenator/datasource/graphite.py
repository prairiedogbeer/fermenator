from . import DataSource, DataNotFoundError
import requests
from collections import deque

class GraphiteDataSource(DataSource):
    """
    A graphite data source. This class only implements get operations,
    since set type operations must be made against a totally different API
    (carbon).
    """

    def __init__(self, **kwargs):
        if not 'url' in kwargs:
            raise RuntimeError("url must be provided in kwargs")
        else:
            self.url = kwargs['url'].rstrip('/')
        self._config = kwargs
        if 'user' in kwargs and 'password' in kwargs:
            self.auth = (kwargs['user'].strip(), kwargs['password'].strip())
        else:
            self.auth = None

    def get(self, key, time_limit_s=60*5):
        url = self._build_url(key, time_limit_s)
        result = requests.get(url, auth=self.auth)
        try:
            raw_results = result.json()[0]['datapoints']
            raw_results.reverse()
            for row in raw_results:
                yield row
        except IndexError:
            raise DataNotFoundError("tried to read data that doesn't exist at {}".format(
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
