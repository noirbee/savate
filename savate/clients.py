# -*- coding: utf-8 -*-

from savate.helpers import HTTPEventHandler, event_mask_str
from savate import looping

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

    def flush(self):
        HTTPEventHandler.flush(self)
        if self.output_buffer.ready:
            # De-activate handler to avoid unnecessary notifications
            self.server.loop.register(self, 0)

    def handle_event(self, eventmask):
        if eventmask & looping.POLLOUT:
            self.flush()
        elif eventmask & (looping.POLLERR | looping.POLLHUP):
            # Error / Hangup, client probably closed connection
            self.close()
        else:
            self.server.logger.error('%s: unexpected eventmask %d (%s)', self, eventmask, event_mask_str(eventmask))
