# -*- coding: utf-8 -*-

from savate.helpers import Buffer
from savate.sources import LowBitrateSource
from savate.mp3 import MP3Parser
from savate.adts import ADTSParser


class ShoutcastSource(LowBitrateSource):

    ICY_HEADERS = ('name', 'genre', 'url', 'pub', 'br', 'metaint', 'notice1',
                   'notice2')
    FRAME_PARSER_CLASS = None

    def __init__(self, server, sock, address, content_type,
                 request_parser, path = None, burst_size = None,
                 on_demand=False):
        LowBitrateSource.__init__(self, server, sock, address, content_type,
                                   request_parser, path, burst_size, on_demand)

        self.set_headers()

        self.frame_parser = self.FRAME_PARSER_CLASS
        if self.frame_parser is not None:
            self.frame_parser = self.frame_parser()

    def set_headers(self):
        # set icy metadata
        for head in self.ICY_HEADERS:
            setattr(self, 'icy_%s' % head,
                    self.request_parser.headers.get('Icy-%s' % head.capitalize()))

        if self.icy_metaint:
            self.icy_metaint = int(self.icy_metaint)
            # bytes count for metadata
            self.bytes_count = 0
            self.buffer_metadata = b''
            self.metadata = b''

    def on_demand_deactivate(self):
        LowBitrateSource.on_demand_deactivate(self)
        if self.frame_parser is not None:
            self.frame_parser.clear()

    def on_demand_connected(self, sock, request_parser):
        # update? headers
        LowBitrateSource.on_demand_connected(self, sock, request_parser)
        self.set_headers()

    def metadata_parse(self):
        packet_cuts = []
        packet = Buffer(self.output_buffer_data )

        while packet:
            if self.bytes_count < 0:
                # we need to get some metadata
                metadata = packet[:-self.bytes_count]
                packet = packet[-self.bytes_count:]
                self.buffer_metadata += metadata.tobytes()
                self.bytes_count += len(metadata)
                if self.bytes_count == 0:
                    self.metadata = self.buffer_metadata
                    self.buffer_metadata = b''
            elif self.icy_metaint - self.bytes_count == 0:
                # we get metadata size
                self.bytes_count = (-ord(packet[0]) << 4) - 1
            else:
                mp3 = packet[:self.icy_metaint - self.bytes_count]
                packet = packet[self.icy_metaint - self.bytes_count:]
                self.bytes_count += len(mp3)
                packet_cuts.append(mp3)

        self.output_buffer_data = b''.join(cut.tobytes() for cut in packet_cuts)

    def handle_packet(self, packet):
        self.output_buffer_data += packet

        if self.icy_metaint:
            self.metadata_parse()

        if not self.output_buffer_data:
            return

        if self.frame_parser is not None:
            packet = self.frame_parser.feed(self.output_buffer_data)
        else:
            packet = self.output_buffer_data
        self.output_buffer_data= b''

        if packet:
            self.publish_packet(packet)
            self.burst_packets.append(packet)


class MP3ShoutcastSource(ShoutcastSource):
    """Shoutcast Source with MP3 frames parsing support."""
    FRAME_PARSER_CLASS = MP3Parser


class ADTSShoutcastSource(ShoutcastSource):
    """Shoutcast Source with ADTS frames parsing support."""
    FRAME_PARSER_CLASS = ADTSParser
