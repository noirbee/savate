# -*- coding: utf-8 -*-

from savate.helpers import HTTPEventHandler, HTTPResponse


class StreamClient(HTTPEventHandler):

    def __init__(self, server, source, sock, address, request_parser, content_type):
        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  HTTPResponse(200, b'OK', {b'Content-Length': None,
                                               b'Content-Type': content_type}))
        self.source = source

    def add_packet(self, packet):
        self.output_buffer.add_buffer(packet)

    def close(self):
        self.server.remove_client(self)
        HTTPEventHandler.close(self)

    def finish(self):
        # This is a no-op, since we never really know when we end the
        # connection (it's up to the stream source)
        pass

    def flush(self):
        HTTPEventHandler.flush(self)
        if self.output_buffer.ready:
            # De-activate handler to avoid unnecessary notifications
            self.server.loop.register(self, 0)
