# -*- coding: utf-8 -*-

from helpers import HTTPEventHandler
import looping
import buffer_event
import pprint

class StatusClient(HTTPEventHandler):

    def __init__(self, server, sock, address, request_parser):
        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  200, b'OK', {}, pprint.pformat(server.sources))

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
            self.output_buffer.flush()

    def handle_event(self, eventmask):
        if eventmask & looping.POLLOUT:
            self.output_buffer.flush()
        else:
            print 'Unexpected eventmask %s' % (eventmask)
