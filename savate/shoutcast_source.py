import socket
from typing import TYPE_CHECKING, ClassVar, Optional, Type

from cyhttp11 import HTTPParser

from savate.sources import LowBitrateSource
from savate.audio_parser import AbstractAudioParser
from savate.mp3 import MP3Parser
from savate.adts import ADTSParser
if TYPE_CHECKING:
    from savate.server import TCPServer


class ShoutcastSource(LowBitrateSource):

    ICY_HEADERS = (b'name', b'genre', b'url', b'pub', b'br', b'metaint', b'notice1',
                   b'notice2')
    FRAME_PARSER_CLASS: ClassVar[Type[AbstractAudioParser]]

    def __init__(self, server: "TCPServer", sock: socket.socket, address: tuple[str, int], content_type: str,
                 request_parser: HTTPParser, path: Optional[str] = None, burst_size: Optional[int] = None,
                 on_demand: bool = False, keepalive: Optional[int] = None) -> None:
        super().__init__(server, sock, address, content_type,
                                  request_parser, path, burst_size, on_demand,
                                  keepalive)

        self.icy_headers: dict[bytes, bytes] = {}
        self.icy_metaint: int = 0
        self.set_headers()

        self.frame_parser = self.FRAME_PARSER_CLASS()
        self.working_buffer = self.output_buffer_data
        self.output_buffer_data = b''

    def set_headers(self) -> None:
        # set icy metadata
        for head in self.ICY_HEADERS:
            header_name = b'Icy-%s' % head.capitalize()
            self.icy_headers[header_name] = self.request_parser.headers.get(header_name)

        import logging; logging.getLogger(__name__).error("ICY HEADERS: %s", self.icy_headers)
        if self.icy_headers.get(b"Icy-Metaint"):
            self.icy_metaint = int(self.icy_headers[b"Icy-Metaint"])
            # bytes count for metadata
            self.bytes_count = 0
            self.buffer_metadata = b''
            self.metadata = b''

    def on_demand_deactivate(self) -> None:
        LowBitrateSource.on_demand_deactivate(self)
        self.working_buffer = b''
        self.frame_parser.clear()

    def on_demand_connected(self, sock: socket.socket, request_parser: HTTPParser) -> None:
        # update? headers
        super().on_demand_connected(sock, request_parser)
        self.set_headers()

    def metadata_parse(self) -> None:
        packet_cuts = []
        packet = memoryview(self.working_buffer)

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
                self.bytes_count = (-packet[0] << 4) - 1
            else:
                mp3 = packet[:self.icy_metaint - self.bytes_count]
                packet = packet[self.icy_metaint - self.bytes_count:]
                self.bytes_count += len(mp3)
                packet_cuts.append(mp3)

        self.working_buffer = b''.join(cut.tobytes() for cut in packet_cuts)

    def handle_packet(self, packet: bytes) -> None:
        self.working_buffer += packet

        if self.icy_metaint:
            self.metadata_parse()

        if not self.working_buffer:
            return

        if self.frame_parser is not None:
            self.output_buffer_data += self.frame_parser.feed(self.working_buffer)
        else:
            self.output_buffer_data += self.working_buffer
        self.working_buffer = b''

        if len(self.output_buffer_data) > self.TEMP_BUFFER_SIZE:
            self.publish_packet(self.output_buffer_data)
            self.burst_packets.append(self.output_buffer_data)
            self.output_buffer_data = b''


class MP3ShoutcastSource(ShoutcastSource):
    """Shoutcast Source with MP3 frames parsing support."""
    FRAME_PARSER_CLASS = MP3Parser


class ADTSShoutcastSource(ShoutcastSource):
    """Shoutcast Source with ADTS frames parsing support."""
    FRAME_PARSER_CLASS = ADTSParser
