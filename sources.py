# -*- coding: utf-8 -*-

import helpers
import looping
import collections
import math

class StreamSource(looping.BaseIOEventHandler):

    # Incoming maximum buffer size
    RECV_BUFFER_SIZE = 64 * 2**10

    def __init__(self, server, sock, address, content_type, request_parser):
        self.server = server
        self.sock = sock
        self.address = address
        self.content_type = content_type
        self.request_parser = request_parser
        self.path = self.request_parser.request_path

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            while True:
                packet = helpers.handle_eagain(self.sock.recv, self.RECV_BUFFER_SIZE)
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

    def publish_packet(self, packet):
        self.server.publish_packet(self, packet)

    def new_client(self, client):
        # Do nothing by default
        pass

class BufferedRawSource(StreamSource):

    # Temporary buffer size
    TEMP_BUFFER_SIZE = 4 * 2**10

    # Size of initial data burst for clients
    BURST_SIZE = 32 * 2**10

    def __init__(self, server, sock, address, content_type, request_parser):
        StreamSource.__init__(self, server, sock, address, content_type, request_parser)
        self.output_buffer_data = request_parser.body
        self.burst_packets = collections.deque([self.buffer_data], math.ceil(float(self.BURST_SIZE) / float(self.TEMP_BUFFER_SIZE)))

    def publish_packet(self, packet):
        self.output_buffer_data = self.output_buffer_data + packet
        if len(self.output_buffer_data) >= self.TEMP_BUFFER_SIZE:
            StreamSource.publish_packet(self, self.output_buffer_data)
            self.burst_packets.append(self.output_buffer_data)
            self.output_buffer_data = ''

    def new_client(self, client):
        for packet in self.burst_packets:
            client.add_packet(packet)

from flv_source import FLVSource

sources_mapping = {
    b'video/x-flv': FLVSource,
    b'audio/x-hx-aac-adts': BufferedRawSource,
    b'application/octet-stream': BufferedRawSource,
    }
