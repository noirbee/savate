# -*- coding: utf-8 -*-

import helpers
import looping
import collections
# import flv

class StreamSource(looping.BaseIOEventHandler):

    def __init__(self, server, sock, address, request_parser):
        self.server = server
        self.sock = sock
        self.address = address
        self.request_parser = request_parser
        self.path = self.request_parser.request_path

    def publish_packet(self, packet):
        self.server.publish_packet(self, packet)

    def new_client(self, client):
        # Do nothing by default
        pass

class BufferedRawSource(StreamSource):

    # Approximately one packet/s for a 64 kb/s stream
    PACKET_SIZE = 8192

    def __init__(self, server, sock, address, request_parser):
        StreamSource.__init__(self, server, sock, address, request_parser)
        self.buffer_data = ''

    def publish_packet(self, packet):
        self.buffer_data = self.buffer_data + packet
        if len(self.buffer_data) >= self.PACKET_SIZE:
            StreamSource.publish_packet(self, self.buffer_data)
            self.buffer_data = ''

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            while True:
                packet = helpers.handle_eagain(self.sock.recv, self.PACKET_SIZE)
                if packet == None:
                    # EAGAIN
                    break
                elif packet == b'':
                    # End of stream
                    print 'End of stream for %s, %s' % (self.sock, self.address)
                    self.server.remove_source(self)
                    # FIXME: publish "EOS" packet
                    break
                else:
                    self.publish_packet(packet)
        else:
            print 'Unexpected eventmask %s' % (eventmask)

class FLVSource(StreamSource):

    def __init__(self, sock, server, address, request_parser):
        StreamSource.__init__(self, sock, server, address, request_parser)
        self.stream_header = None
        self.initial_tags = []
        self.current_output_buffer = None

    # def handle_event(self, eventmask):
    #     if eventmask & looping.POLLIN:
    #         if self.stream_header


sources_mapping = {
    b'video/x-flv': FLVSource,
    b'audio/x-hx-aac-adts': BufferedRawSource,
    b'application/octet-stream': BufferedRawSource,
    }
