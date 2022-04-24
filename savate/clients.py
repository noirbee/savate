import socket
from typing import TYPE_CHECKING, Optional, Union

from cyhttp11 import HTTPParser

from savate.looping import POLLOUT
from savate.helpers import HTTPEventHandler, HTTPResponse
from savate.sources import StreamSource
if TYPE_CHECKING:
    from savate.server import TCPServer


class StreamClient(HTTPEventHandler):

    def __init__(self, server: "TCPServer", source: StreamSource, sock: socket.socket, address: tuple[str, int], request_parser: HTTPParser,
                 content_type: str, http_response: Optional[HTTPResponse] = None) -> None:
        if http_response is None:
            http_response = HTTPResponse(
                200, b'OK',
                {b'Content-Length': None, b'Content-Type': bytes(content_type, "ascii")},
            )

        super().__init__(server, sock, address, request_parser,
                                  http_response)
        self.source = source
        self.timeout_state = False
        self.server.remove_inactivity_timeout(self)

    @property
    def closed(self) -> bool:
        return self.sock is None

    def activate_timeout(self) -> None:
        if not self.timeout_state:
            self.timeout_state = True
            self.server.reset_inactivity_timeout(self)

    def add_packet(self, packet: bytes) -> None:
        self.output_buffer.add_buffer(packet)
        self.activate_timeout()
        self.server.loop.register(self, POLLOUT)

    def close(self) -> None:
        self.server.remove_client(self)
        super().close()

    def finish(self) -> None:
        # This is a no-op, since we never really know when we end the
        # connection (it's up to the stream source)
        pass

    def flush(self) -> None:
        super().flush()
        if self.output_buffer.ready:
            # De-activate handler to avoid unnecessary notifications
            self.server.loop.register(self, 0)
            # deactivate timer if output_buffer is empty
            self.server.remove_inactivity_timeout(self)
            self.timeout_state = False


class ShoutcastClient(StreamClient):

    ICY_META_INTERVAL = 32 * 2 ** 10

    def __init__(self, server: "TCPServer", source: "ShoutcastSource", sock: socket.socket, address: tuple[str, int], request_parser: HTTPParser,
                 content_type: str, http_response: Optional[HTTPResponse] = None) -> None:
        headers = {b'Content-Length': None, b'Content-Type': bytes(content_type, "ascii")}
        for header in source.ICY_HEADERS:
            if header == b'metaint':
                continue

            header_value = source.icy_headers.get(b'icy_%s' % header)
            if header_value:
                headers[b'icy-%s' % header] = header_value

        # did client asked for metadata ?
        if request_parser.headers.get(b'Icy-Metadata') == b'1' and hasattr(
            source, 'metadata'):
            self.metadata = b''
            self.bytes_count = 0
            self.add_packet = self.add_packet_with_metadata  # type: ignore[assignment]
            headers[b'icy-metaint'] = b'%s' % self.ICY_META_INTERVAL

        super().__init__(server, source, sock, address, request_parser,
                              content_type, HTTPResponse(
                                  200, b'OK',
                                  headers,
                              ))

    def add_packet_with_metadata(self, packet: bytes) -> None:
        packet_cuts = []
        packet = memoryview(packet)

        while packet:
            if self.bytes_count + len(packet) > self.ICY_META_INTERVAL:
                packet_cuts.append(
                    packet[:self.ICY_META_INTERVAL - self.bytes_count])
                packet = packet[self.ICY_META_INTERVAL - self.bytes_count:]
                # insert metadata
                if self.metadata != self.source.metadata:
                    # new metadata
                    self.metadata = self.source.metadata
                    packet_cuts.append(memoryview(self.metadata))
                else:
                    # insert 0
                    packet_cuts.append(memoryview(b'\0'))

                self.bytes_count = 0
            else:
                self.bytes_count += len(packet)
                packet_cuts.append(packet)
                break

        StreamClient.add_packet(
            self, b''.join(cut.tobytes() for cut in packet_cuts))


from savate.shoutcast_source import ShoutcastSource


def find_client(server: "TCPServer", source: StreamSource, sock: socket.socket, address: tuple[str, int], request_parser: HTTPParser) -> StreamClient:
    """Returns a :class:`StreamClient` instance."""
    if isinstance(source, ShoutcastSource):
        return ShoutcastClient(server, source, sock, address, request_parser,
                  source.content_type)

    return StreamClient(server, source, sock, address, request_parser,
                  source.content_type)
