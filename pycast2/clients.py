# -*- coding: utf-8 -*-

import pprint
from pycast2.helpers import HTTPEventHandler
from pycast2 import looping

class StatusClient(HTTPEventHandler):

    def __init__(self, server, sock, address, request_parser):
        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  200, b'OK', {b'Content-Type': 'text/plain'},
                                  pprint.pformat(server.sources))

class StreamClient(HTTPEventHandler):

    def __init__(self, server, source, sock, address, request_parser, content_type):
        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  200, b'OK', {b'Content-Length': None,
                                               b'Content-Type': content_type})
        self.source = source

    def add_packet(self, packet):
        self.output_buffer.add_buffer(packet)

    def close(self):
        self.server.remove_client(self)
        HTTPEventHandler.close(self)

    def flush_if_ready(self):
        if self.output_buffer.ready:
            self.flush()

    def handle_event(self, eventmask):
        if eventmask & looping.POLLOUT:
            self.flush()
        else:
            self.server.logger.error('%s: unexpected eventmask %s', self, eventmask)
