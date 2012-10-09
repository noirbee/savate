# -*- coding: utf-8 -*-

import socket

from savate import helpers
from savate import looping


class StreamSource(looping.BaseIOEventHandler):

    # Incoming maximum buffer size
    RECV_BUFFER_SIZE = 64 * 2**10
    # Socket low water mark
    RECV_LOW_WATER_MARK = 32 * 2**10
    # Stay connected for 20 seconds to the source when all clients are
    # disconnected
    ON_DEMAND_TIMEOUT = 20

    # ondemand states
    DISABLED = 0
    STOPPED = 1
    CONNECTING = 2
    RUNNING = 3
    CLOSING = 4  # running but about to close

    def __init__(self, server, sock, address, content_type,
                 request_parser = None, path = None, burst_size = None,
                 on_demand = False, keepalive = None):
        self.server = server
        self.sock = sock
        self.address = address
        self.content_type = content_type
        self.request_parser = request_parser
        self.path = path or self.request_parser.request_path
        self.burst_size = burst_size
        self.keepalive = keepalive

        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVLOWAT, self.RECV_LOW_WATER_MARK)

        self.on_demand = self.RUNNING if on_demand else self.DISABLED
        self.relay = server.relays.get(sock)  # some sources doesn't have relay

    def on_demand_activate(self):
        """Method which reconnects the relay"""
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

    def on_demand_deactivate(self):
        """Cleanup when on_demand is deactivated. It can be overided in
        subclasses to clear buffers for examples.

        """
        self.server.logger.info('Desactivate ondemand for source %s: %s',
                                self.path, self.address)
        self.on_demand = self.STOPPED
        self.server.loop.unregister(self)
        self.server.remove_inactivity_timeout(self)
        self.sock.close()

    def on_demand_connected(self, sock, request_parser):
        """Method called by the relay when it did reconnect sucessfully."""
        self.on_demand = self.RUNNING
        self.sock = sock
        self.request_parser = request_parser
        self.server.loop.register(self, looping.POLLIN)

    def __str__(self):
        return '<%s for %s, %s, %s>' % (
            self.__class__.__name__,
            self.path,
            self.address,
            self.content_type,
            )

    def close(self):
        self.server.remove_source(self)
        self.relay = None  # prevent cyclic reference
        looping.BaseIOEventHandler.close(self)

    def recv_packet(self, buffer_size = RECV_BUFFER_SIZE):
        packet = helpers.handle_eagain(self.sock.recv, buffer_size)
        if packet:
            self.server.update_activity(self)
        return packet

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            while True:
                packet = self.recv_packet(self.RECV_BUFFER_SIZE)
                if packet == None:
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

    def handle_packet(self, packet):
        # By default, we do nothing and directly feed it to
        # publish_packet(). This is meant to be overriden in
        # subclasses.
        self.publish_packet(packet)

    def publish_packet(self, packet):
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

    def new_client(self, client):
        if self.on_demand == self.STOPPED:
            self.on_demand_activate()
        elif self.on_demand == self.CLOSING:
            self.on_demand = self.RUNNING
            self.server.timeouts.remove_timeout(self)

    def update_burst_size(self, new_burst_size):
        pass


class BufferedRawSource(StreamSource):

    # Temporary buffer size
    TEMP_BUFFER_SIZE = 64 * 2**10

    # Size of initial data burst for clients
    BURST_SIZE = 64 * 2**10

    def __init__(self, server, sock, address, content_type,
                 request_parser = None , path = None, burst_size = None,
                 on_demand = False, keepalive = None):
        StreamSource.__init__(self, server, sock, address, content_type,
                              request_parser, path, burst_size, on_demand,
                              keepalive)
        if request_parser:
            self.output_buffer_data = request_parser.body
        else:
            self.output_buffer_data = ''
        if self.burst_size is None:
            self.burst_size = self.BURST_SIZE
        self.burst_packets = helpers.BurstQueue(self.burst_size)

    def handle_packet(self, packet):
        self.output_buffer_data = self.output_buffer_data + packet
        if len(self.output_buffer_data) >= self.TEMP_BUFFER_SIZE:
            self.publish_packet(self.output_buffer_data)
            self.burst_packets.append(self.output_buffer_data)
            self.output_buffer_data = ''

    def on_demand_deactivate(self):
        self.output_buffer_data = b''
        self.burst_packets.clear()
        StreamSource.on_demand_deactivate(self)

    def on_demand_connected(self, sock, request_parser):
        StreamSource.on_demand_connected(self, sock, request_parser)
        self.output_buffer_data = request_parser.body

    def new_client(self, client):
        StreamSource.new_client(self, client)
        for packet in self.burst_packets:
            client.add_packet(packet)

    def update_burst_size(self, new_burst_size):
        if new_burst_size is None:
            new_burst_size = self.BURST_SIZE
        self.burst_size = new_burst_size
        self.burst_packets.maxbytes = new_burst_size


class FixedPacketSizeSource(BufferedRawSource):

    def handle_packet(self, packet):
        self.output_buffer_data = self.output_buffer_data + packet
        if len(self.output_buffer_data) >= self.TEMP_BUFFER_SIZE:
            nb_packets, remaining_bytes = divmod(len(self.output_buffer_data),
                                                 self.PACKET_SIZE)
            if remaining_bytes:
                tmp_data = self.output_buffer_data[:(nb_packets * self.PACKET_SIZE)]
                self.output_buffer_data = self.output_buffer_data[-remaining_bytes:]
            else:
                tmp_data = self.output_buffer_data
                self.output_buffer_data = ''
            self.publish_packet(tmp_data)
            self.burst_packets.append(tmp_data)

class MPEGTSSource(FixedPacketSizeSource):

    MPEGTS_PACKET_SIZE = 188
    PACKET_SIZE = MPEGTS_PACKET_SIZE

    # Incoming maximum buffer size; 188 * 7 = 1316 is the largest
    # multiple of 188 that is smaller than the typical MTU size of
    # 1500
    RECV_BUFFER_SIZE = 7 * MPEGTS_PACKET_SIZE

    TEMP_BUFFER_SIZE = 50 * RECV_BUFFER_SIZE
    BURST_SIZE = 50 * RECV_BUFFER_SIZE

    # Socket low water mark
    RECV_LOW_WATER_MARK = 64 * 2**10


class LowBitrateSource(BufferedRawSource):

    # FIXME: For low bitrates MP3/AAC streams, the default temporary
    # buffer size is too large and causes timeouts in clients; hence
    # the use of a lower value by default

    TEMP_BUFFER_SIZE = 8 * 2**10
    RECV_LOW_WATER_MARK = 2 * 2**10


# Note that recvmmsg() requires Linux >= 2.6.33 and glibc >= 2.12
# FIXME: add a configuration option
try:
    from savate.recvmmsg import recvmmsg

    class MPEGTSSource(MPEGTSSource):
        """
        A specialised MPEG-TS over UDP input class that uses
        recvmmsg() to provide a more efficient alternative than
        multiple recv() calls.
        """

        RECV_BUFFER_COUNT_MIN = 1
        RECV_BUFFER_COUNT_MAX = 512

        def __init__(self, server, sock, address, content_type,
                     request_parser = None, path = None, burst_size = None,
                     on_demand = False, keepalive = None):
            super(MPEGTSSource, self).__init__(server, sock, address,
                                               content_type, request_parser,
                                               path, burst_size, on_demand, keepalive)
            self.recv_buffer_count = self.RECV_BUFFER_COUNT_MIN

        def recv_packet(self, _buffer_size = None):
            # We ignore _buffer_size altogether here
            buffers = [bytearray(self.RECV_BUFFER_SIZE) for i in range(self.recv_buffer_count)]
            buffers = helpers.handle_eagain(recvmmsg, self.sock.fileno(), buffers) or ()
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

sources_mapping = {
    b'video/x-flv': FLVSource,
    b'application/x-flv': FLVSource,
    b'audio/mpeg': MP3ShoutcastSource,
    b'audio/mp3': MP3ShoutcastSource,
    b'audio/aacp': ADTSShoutcastSource,
    b'audio/aac': ADTSShoutcastSource,
    b'application/octet-stream': BufferedRawSource,
    b'video/MP2T': MPEGTSSource,
    b'video/mpeg': MPEGTSSource,
    }


def find_source(server, sock, address, request_parser,
                path = None, burst_size = None, on_demand = False,
                keepalive = None):
    """Return a :class:`StreamSource` instance."""

    content_type = request_parser.headers.get('Content-Type',
                                      'application/octet-stream')
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
