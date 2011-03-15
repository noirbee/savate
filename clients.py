# -*- coding: utf-8 -*-

from helpers import HTTPEventHandler
import looping
import buffer_event

class StatusClient(HTTPEventHandler):

    def __init__(self, server, sock, address, request_parser):
        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  204, b'No content')

class StreamClient(HTTPEventHandler):

    def __init__(self, server, source, sock, address, request_parser):
        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  200, b'OK', {b'Content-Length': None})
        self.source = source

    def add_packet(self, packet):
        self.output_buffer.add_buffer(packet)

    def flush_if_ready(self):
        # print 'buffer is ready: %s' % (self.output_buffer.ready)
        if self.output_buffer.ready:
            self.output_buffer.flush()

    def handle_event(self, eventmask):
        if eventmask & looping.POLLOUT:
            # print 'lol I can write, %d items in buffer' % (len(self.output_buffer.buffer_queue))
            self.output_buffer.flush()
        else:
            print 'Unexpected eventmask %s' % (eventmask)
