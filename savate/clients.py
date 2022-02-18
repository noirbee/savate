# -*- coding: utf-8 -*-

from savate.looping import POLLOUT
from savate.helpers import HTTPEventHandler, HTTPResponse
from savate.sources import ShoutcastSource


class StreamClient(HTTPEventHandler):

    def __init__(self, server, source, sock, address, request_parser,
                 content_type, http_response = None):
        if http_response is None:
            http_response = HTTPResponse(
                200, b'OK',
                {b'Content-Length': None, b'Content-Type': content_type},
            )

        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  http_response)
        self.source = source
        self.timeout_state = False
        self.server.remove_inactivity_timeout(self)

    @property
    def closed(self):
        return self.sock is None

    def activate_timeout(self):
        if not self.timeout_state:
            self.timeout_state = True
            self.server.reset_inactivity_timeout(self)

    def add_packet(self, packet):
        self.output_buffer.add_buffer(packet)
        self.activate_timeout()
        self.server.loop.register(self, POLLOUT)

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
            # deactivate timer if output_buffer is empty
            self.server.remove_inactivity_timeout(self)
            self.timeout_state = False


class ShoutcastClient(StreamClient):

    ICY_META_INTERVAL = 32 * 2 ** 10

    def __init__(self, server, source, sock, address, request_parser,
                 content_type):
        headers = {b'Content-Length': None, b'Content-Type': content_type}
        for header in source.ICY_HEADERS:
            if header == 'metaint':
                continue

            header_value = getattr(source, 'icy_%s' % header)
            if header_value:
                headers[b'icy-%s' % header] = header_value

        # did client asked for metadata ?
        if request_parser.headers.get('Icy-Metadata') == b'1' and hasattr(
            source, 'metadata'):
            self.metadata = b''
            self.bytes_count = 0
            self.add_packet = self.add_packet_with_metadata
            headers[b'icy-metaint'] = b'%s' % self.ICY_META_INTERVAL

        StreamClient.__init__(self, server, source, sock, address, request_parser,
                              content_type, HTTPResponse(
                                  200, b'OK',
                                  headers,
                              ))

    def add_packet_with_metadata(self, packet):
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


def find_client(server, source, sock, address, request_parser):
    """Returns a :class:`StreamClient` instance."""
    if isinstance(source, ShoutcastSource):
        client = ShoutcastClient
    else:
        client = StreamClient

    return client(server, source, sock, address, request_parser,
                  source.content_type)
