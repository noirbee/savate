import socket
from typing import TYPE_CHECKING, ClassVar, Optional, Type, cast

from cyhttp11 import HTTPParser

from savate import helpers
from savate import looping
if TYPE_CHECKING:
    from savate.clients import StreamClient
    from savate.server import TCPServer


class StreamSource(looping.BaseIOEventHandler):

    # Incoming maximum buffer size
    RECV_BUFFER_SIZE = 64 * 2**10
    # Socket low water mark
    RECV_LOW_WATER_MARK = 1
    # Stay connected for 20 seconds to the source when all clients are
    # disconnected
    ON_DEMAND_TIMEOUT = 20

    # ondemand states
    DISABLED = 0
    STOPPED = 1
    CONNECTING = 2
    RUNNING = 3
    CLOSING = 4  # running but about to close

    def __init__(self, server: "TCPServer", sock: socket.socket, address: tuple[str, int], content_type: str,
                 request_parser: HTTPParser, path: Optional[str] = None, burst_size: Optional[int] = None,
                 on_demand: bool = False, keepalive: Optional[int] = None) -> None:
        self.server = server
        self.sock = sock
        self.address = address
        self.content_type = content_type
        self.request_parser = request_parser
        if not path:
            if not request_parser:
                raise Exception("Cannot use a source without either path or an HTTP parser")
            self.path = request_parser.path
        else:
            self.path = path
        self.burst_size = burst_size
        self.keepalive = keepalive

        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVLOWAT, self.RECV_LOW_WATER_MARK)

        self.on_demand = self.RUNNING if on_demand else self.DISABLED
        self.relay = server.relays.get(sock)  # some sources doesn't have relay

    def on_demand_activate(self) -> None:
        """Method which reconnects the relay"""
        if not self.relay:
            raise Exception("Calling on_demand_activate() on source without a relay")
        # activate only if state 1
        if self.on_demand == self.CLOSING:
            # cancel on-demand closing
            self.server.timeouts.remove_timeout(self)
            self.on_demand = self.RUNNING
            return
        elif self.on_demand != self.STOPPED:
            return

        self.server.logger.info('Activate ondemand for source %s: %s',
                                self.path, self.address)
        self.on_demand = self.CONNECTING
        del self.server.relays[self.sock]
        self.relay.connect()
        self.server.relays[self.relay.sock] = self.relay

    def on_demand_deactivate(self) -> None:
        """Cleanup when on_demand is deactivated. It can be overided in
        subclasses to clear buffers for examples.

        """
        self.server.logger.info('Desactivate ondemand for source %s: %s',
                                self.path, self.address)
        self.on_demand = self.STOPPED
        self.server.loop.unregister(self)
        self.server.remove_inactivity_timeout(self)
        self.sock.close()

    def on_demand_connected(self, sock: socket.socket, request_parser: HTTPParser) -> None:
        """Method called by the relay when it did reconnect sucessfully."""
        self.on_demand = self.RUNNING
        self.sock = sock
        self.request_parser = request_parser
        self.server.loop.register(self, looping.POLLIN)

    def __str__(self) -> str:
        return '<%s for %s, %s, %s>' % (
            self.__class__.__name__,
            self.path,
            self.address,
            self.content_type,
            )

    def close(self) -> None:
        self.server.remove_source(self)
        self.relay = None  # prevent cyclic reference
        looping.BaseIOEventHandler.close(self)

    def recv_packet(self, buffer_size: int = RECV_BUFFER_SIZE) -> Optional[bytes]:
        packet = helpers.handle_eagain(self.sock.recv, buffer_size)
        if packet:
            self.server.update_activity(self)
        return packet

    def handle_event(self, eventmask: int) -> None:
        if eventmask & looping.POLLIN:
            while True:
                packet = self.recv_packet(self.RECV_BUFFER_SIZE)
                if packet is None:
                    # EAGAIN
                    break
                elif packet == b'':
                    # End of stream
                    self.server.logger.warn('End of stream for %s', self)
                    self.close()
                    # FIXME: publish "EOS" packet
                    break
                else:
                    self.handle_packet(packet)
                    if len(packet) < self.RECV_BUFFER_SIZE:
                        # High chances we would get EAGAIN on the next
                        # iteration. We'll be called again soon if
                        # there is still data available.
                        break
        else:
            self.server.logger.error('%s: unexpected eventmask %s', self, eventmask)

    def handle_packet(self, packet: bytes) -> None:
        # By default, we do nothing and directly feed it to
        # publish_packet(). This is meant to be overriden in
        # subclasses.
        self.publish_packet(packet)

    def publish_packet(self, packet: bytes) -> None:
        clients = self.server.sources[self.path][self]['clients']

        if not clients and self.on_demand == self.RUNNING:
            # activate timeout for desactivating source
            self.on_demand = self.CLOSING
            self.server.timeouts.reset_timeout(
                self,
                self.server.loop.now() + self.ON_DEMAND_TIMEOUT,
                self.on_demand_deactivate,
            )

        self.server.publish_packet(self, packet)

    def new_client(self, client: "StreamClient") -> None:
        if self.on_demand == self.STOPPED:
            self.on_demand_activate()
        elif self.on_demand == self.CLOSING:
            self.on_demand = self.RUNNING
            self.server.timeouts.remove_timeout(self)

    def update_burst_size(self, new_burst_size: Optional[int]) -> None:
        pass


class BufferedRawSource(StreamSource):

    # Temporary buffer size
    TEMP_BUFFER_SIZE = 64 * 2**10

    # Size of initial data burst for clients
    BURST_SIZE = 64 * 2**10

    output_buffer_data: bytes

    def __init__(self, server: "TCPServer", sock: socket.socket, address: tuple[str, int], content_type: str,
                 request_parser: Optional[HTTPParser] = None, path: Optional[str] = None, burst_size: Optional[int] = None,
                 on_demand: bool = False, keepalive: Optional[int] = None) -> None:
        super().__init__(server, sock, address, content_type,
                       request_parser, path, burst_size, on_demand,
                       keepalive)
        if request_parser:
            self.output_buffer_data = request_parser.body
        else:
            self.output_buffer_data = b''
        if self.burst_size is None:
            self.burst_size = self.BURST_SIZE
        self.burst_packets = helpers.BurstQueue(self.burst_size)

    def handle_packet(self, packet: bytes) -> None:
        self.output_buffer_data = self.output_buffer_data + packet
        if len(self.output_buffer_data) >= self.TEMP_BUFFER_SIZE:
            self.publish_packet(self.output_buffer_data)
            self.burst_packets.append(self.output_buffer_data)
            self.output_buffer_data = b''

    def on_demand_deactivate(self) -> None:
        self.output_buffer_data = b''
        self.burst_packets.clear()
        StreamSource.on_demand_deactivate(self)

    def on_demand_connected(self, sock: socket.socket, request_parser: HTTPParser) -> None:
        StreamSource.on_demand_connected(self, sock, request_parser)
        self.output_buffer_data = request_parser.body

    def new_client(self, client: "StreamClient") -> None:
        super().new_client(client)
        for packet in self.burst_packets:
            client.add_packet(packet)

    def update_burst_size(self, new_burst_size: Optional[int]) -> None:
        if new_burst_size is None:
            new_burst_size = self.BURST_SIZE
        self.burst_size = new_burst_size
        self.burst_packets.maxbytes = new_burst_size


class FixedPacketSizeSource(BufferedRawSource):

    PACKET_SIZE: ClassVar[int]

    def handle_packet(self, packet: bytes) -> None:
        self.output_buffer_data = self.output_buffer_data + packet
        if len(self.output_buffer_data) >= self.TEMP_BUFFER_SIZE:
            nb_packets, remaining_bytes = divmod(len(self.output_buffer_data),
                                                 self.PACKET_SIZE)
            if remaining_bytes:
                tmp_data = self.output_buffer_data[:(nb_packets * self.PACKET_SIZE)]
                self.output_buffer_data = self.output_buffer_data[-remaining_bytes:]
            else:
                tmp_data = self.output_buffer_data
                self.output_buffer_data = b''
            self.publish_packet(tmp_data)
            self.burst_packets.append(tmp_data)


class MPEGTSSource(FixedPacketSizeSource):

    MPEGTS_PACKET_SIZE = 188
    PACKET_SIZE = MPEGTS_PACKET_SIZE

    # Incoming maximum buffer size; 188 * 7 = 1316 is the largest
    # multiple of 188 that is smaller than the typical MTU size of
    # 1500
    RECV_BUFFER_SIZE = 50 * 7 * MPEGTS_PACKET_SIZE

    TEMP_BUFFER_SIZE = 2 * RECV_BUFFER_SIZE
    BURST_SIZE = 2 * RECV_BUFFER_SIZE

    # Socket low water mark
    RECV_LOW_WATER_MARK = 1


class LowBitrateSource(BufferedRawSource):

    # FIXME: For low bitrates MP3/AAC streams, the default temporary
    # buffer size is too large and causes timeouts in clients; hence
    # the use of a lower value by default

    TEMP_BUFFER_SIZE = 8 * 2**10
    RECV_LOW_WATER_MARK = 1


# Note that recvmmsg() requires Linux >= 2.6.33 and glibc >= 2.12
# FIXME: add a configuration option
try:
    from savate.recvmmsg import recvmmsg

    class MPEGTSSource(MPEGTSSource):  # type: ignore[no-redef]
        """
        A specialised MPEG-TS over UDP input class that uses
        recvmmsg() to provide a more efficient alternative than
        multiple recv() calls.
        """

        RECV_BUFFER_COUNT_MIN = 1
        RECV_BUFFER_COUNT_MAX = 512

        def __init__(self, server: "TCPServer", sock: socket.socket, address: tuple[str, int], content_type: str,
                 request_parser: Optional[HTTPParser] = None, path: Optional[str] = None, burst_size: Optional[int] = None,
                 on_demand: bool = False, keepalive: Optional[int] = None) -> None:
            super().__init__(server, sock, address,
                                               content_type, request_parser,
                                               path, burst_size, on_demand, keepalive)
            self.recv_buffer_count = self.RECV_BUFFER_COUNT_MIN

        def recv_packet(self, buffer_size: int = -1) -> Optional[bytes]:
            # We ignore buffer_size altogether here
            recv_buffers = [bytearray(self.RECV_BUFFER_SIZE) for i in range(self.recv_buffer_count)]
            buffers = helpers.handle_eagain(recvmmsg, self.sock.fileno(), recv_buffers)
            if buffers is None:
                return None
            if not buffers:
                return b''
            # Automagically grow/shrink the buffer count as needed
            if len(buffers) >= self.recv_buffer_count:
                self.recv_buffer_count = min(self.recv_buffer_count * 2, self.RECV_BUFFER_COUNT_MAX)
            else:
                self.recv_buffer_count = max(len(buffers), self.RECV_BUFFER_COUNT_MIN)

            self.server.update_activity(self)
            return b''.join(buffers)


except ImportError:
    # recvmmsg() is not available, we'll use regular recv() instead
    pass


from savate.flv_source import FLVSource
from savate.shoutcast_source import (
    ShoutcastSource, MP3ShoutcastSource, ADTSShoutcastSource,
)

sources_mapping: dict[str, Type[StreamSource]] = {
    'video/x-flv': FLVSource,
    'application/x-flv': FLVSource,
    'audio/mpeg': MP3ShoutcastSource,
    'audio/mp3': MP3ShoutcastSource,
    'audio/aacp': ADTSShoutcastSource,
    'audio/aac': ADTSShoutcastSource,
    'application/octet-stream': BufferedRawSource,
    'video/MP2T': MPEGTSSource,
    'video/mpeg': MPEGTSSource,
    }


def find_source(server: "TCPServer", sock: socket.socket, address: tuple[str, int],
                 request_parser: HTTPParser, path: Optional[str] = None, burst_size: Optional[int] = None,
                 on_demand: bool = False, keepalive: Optional[int] = None) -> StreamSource:
    """Return a :class:`StreamSource` instance."""

    content_type = request_parser.headers.get(b'Content-Type',
                                              b'application/octet-stream').decode("ascii")
    if content_type in sources_mapping:
        stream_source = sources_mapping[content_type]
    else:
        server.logger.warning(
            'No registered source handler for %s, using generic handler',
            content_type,
        )
        stream_source = BufferedRawSource

    return stream_source(server, sock, address, content_type, request_parser,
                         path, burst_size, on_demand, keepalive)
