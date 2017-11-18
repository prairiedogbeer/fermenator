"""
This module contains classes for customized logging to third party systems like
slack.
"""
import os
import logging
from slackclient import SlackClient

class SlackLogHandler(logging.Handler):
    """
    Logs messages to Slack if the SLACK_API_TOKEN envvar is present and
    a successful connection is established. If not, exceptions will be
    suppressed and no logging will occur from this handler. The slack channel is
    configurable with :meth:`slack_channel`, and as with other handlers,
    the minimum log level required posted to slack can be set with the inherited
    :meth:`setLevel` method, and defaults to :attr:`logging.ERROR`.
    """

    color_map = {
        'DEBUG': '#009000',
        'INFO': '#ADD8E6',
        'WARNING': '#FFA500',
        'ERROR': '#CC0000',
        'CRITICAL': '#FF00FF'
    }

    def __init__(self, *args, **kwargs):
        super(SlackLogHandler, self).__init__(*args, **kwargs)
        self.log = logging.getLogger(
            "{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__))
        self.slack_channel = kwargs.pop('slack_channel', None)
        self.setLevel(logging.ERROR)
        try:
            self._slack_client = SlackClient(os.environ['SLACK_API_TOKEN'])
        except KeyError:
            self.log.warning(
                "No SLACK_API_TOKEN found in environment, logging disabled")
            self._slack_client = None

    def _get_color(self, log_level_name):
        return self.color_map.get(log_level_name, "WARNING")

    def emit(self, record):
        """
        Implements sending the log message to Slack.
        """
        try:
            if self._slack_client:
                text = self.format(record)
                msg = {
                    'fallback': text,
                    'color': self._get_color(record.levelname),
                    'text': text,
                    'footer': record.name
                }
                self._slack_client.api_call(
                    "chat.postEphemeral",
                    channel=self.slack_channel,
                    #TODO: remove
                    user="U0R3Q7B8R", # gerad
                    attachments=[msg],
                    as_user=True
                )
        except Exception:
            self.handleError(record)
