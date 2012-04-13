# -*- coding: utf-8 -*-

from datetime import datetime


class ApacheLogger(object):
    """Simple stat handler that just log requests in an Apache like format.

    """
    def __init__(self, server, **config):
        self.server = server

    def request_in(self, request_parser, sock):
        pass

    def request_out(self, request_parser, sock, address, size=0, connect_time=None,
                           status_code=200):
        self.server.logger.info(
            '%s - %s [%s] "%s %s %s" %d %s "%s" "%s"',
            address[0],
            '-',  # FIXME: replace by the username
            datetime.fromtimestamp(
                self.server.loop.now(),
            ).strftime("%d/%b/%Y:%H:%M:%S +0000"),  # FIXME: make this timezone aware
            request_parser.request_method,
            request_parser.request_path,
            request_parser.http_version,
            status_code,
            size if size > 0 else '-',
            request_parser.headers.get('Referer', '-'),
            request_parser.headers.get('User-Agent', '-'),
        )
