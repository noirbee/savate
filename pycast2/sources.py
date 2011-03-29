# -*- coding: utf-8 -*-

import helpers
import looping
import math

class StreamSource(looping.BaseIOEventHandler):

    # Incoming maximum buffer size
    RECV_BUFFER_SIZE = 64 * 2**10

    def __init__(self, server, sock, address, content_type, request_parser, path = None):
        self.server = server
        self.sock = sock
        self.address = address
        self.content_type = content_type
        self.request_parser = request_parser
        self.path = path or self.request_parser.request_path

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            while True:
                packet = helpers.handle_eagain(self.sock.recv, self.RECV_BUFFER_SIZE)
                if packet == None:
                    # EAGAIN
                    break
                elif packet == b'':
                    # End of stream
                    self.server.logger.warn('End of stream for %s, %s', self.path, (self.sock, self.address))
                    self.server.remove_source(self)
                    # FIXME: publish "EOS" packet
                    break
                else:
                    self.publish_packet(packet)
        else:
            self.server.logger.error('%s: unexpected eventmask %s', self, eventmask)

    def publish_packet(self, packet):
        self.server.publish_packet(self, packet)

    def new_client(self, client):
        # Do nothing by default
        pass

class BufferedRawSource(StreamSource):

    # Temporary buffer size
    TEMP_BUFFER_SIZE = 64 * 2**10

    # Size of initial data burst for clients
    BURST_SIZE = 64 * 2**10

    def __init__(self, server, sock, address, content_type, request_parser, path = None):
        StreamSource.__init__(self, server, sock, address, content_type, request_parser, path)
        self.output_buffer_data = request_parser.body
        self.burst_packets = helpers.BurstQueue(self.BURST_SIZE)

    def publish_packet(self, packet):
        self.output_buffer_data = self.output_buffer_data + packet
        if len(self.output_buffer_data) >= self.TEMP_BUFFER_SIZE:
            StreamSource.publish_packet(self, self.output_buffer_data)
            self.burst_packets.append(self.output_buffer_data)
            self.output_buffer_data = ''

    def new_client(self, client):
        for packet in self.burst_packets:
            client.add_packet(packet)

class FixedPacketSizeSource(BufferedRawSource, StreamSource):

    def publish_packet(self, packet):
        self.output_buffer_data = self.output_buffer_data + packet
        if len(self.output_buffer_data) >= self.TEMP_BUFFER_SIZE:
            nb_packets, remaining_bytes = divmod(len(self.output_buffer_data),
                                                 self.PACKET_SIZE)
            if remaining_bytes:
                tmp_data = self.output_buffer_data[nb_packets * self.PACKET_SIZE:]
                self.output_buffer_data = self.output_buffer_data[-remaining_bytes:]
            else:
                tmp_data = self.output_buffer_data
                self.output_buffer_data = ''
            StreamSource.publish_packet(self, tmp_data)
            self.burst_packets.append(tmp_data)

class MPEGTSSource(FixedPacketSizeSource):

    MPEGTS_PACKET_SIZE = 188
    PACKET_SIZE = MPEGTS_PACKET_SIZE

from flv_source import FLVSource

sources_mapping = {
    b'video/x-flv': FLVSource,
    b'application/x-flv': FLVSource,
    b'audio/x-hx-aac-adts': BufferedRawSource,
    b'application/octet-stream': BufferedRawSource,
    b'video/MP2T': MPEGTSSource,
    }
