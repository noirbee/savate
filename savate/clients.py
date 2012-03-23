# -*- coding: utf-8 -*-

from savate.helpers import HTTPEventHandler, HTTPResponse, Buffer


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

    def add_packet(self, packet):
        self.output_buffer.add_buffer(packet)

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
        packet = Buffer(packet)

        while packet:
            if self.bytes_count + len(packet) > self.ICY_META_INTERVAL:
                packet_cuts.append(
                    packet[:self.ICY_META_INTERVAL - self.bytes_count])
                packet = packet[self.ICY_META_INTERVAL - self.bytes_count:]
                # insert metadata
                if self.metadata != self.source.metadata:
                    # new metadata
                    self.metadata = self.source.metadata
                    packet_cuts.append(Buffer(self.metadata))
                else:
                    # insert 0
                    packet_cuts.append(Buffer(b'\0'))

                self.bytes_count = 0
            else:
                self.bytes_count += len(packet)
                packet_cuts.append(packet)
                break

        StreamClient.add_packet(
            self, b''.join(cut.tobytes() for cut in packet_cuts))


def find_client(server, source, sock, address, request_parser):
    """Returns a :class:`StreamClient` instance."""
    if source.request_parser.headers.get('Content-Type') == b'audio/mpeg':
        client = ShoutcastClient
    else:
        client = StreamClient

    return client(server, source, sock, address, request_parser,
                        source.content_type)
