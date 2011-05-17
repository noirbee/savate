# -*- coding: utf-8 -*-

import os
try:
    import json
except ImportError:
    import simplejson as json
import pprint
from savate.helpers import HTTPEventHandler, event_mask_str
from savate import looping

class StatusClient(HTTPEventHandler):

    def __init__(self, server, sock, address, request_parser):
        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  200, b'OK', {b'Content-Type': 'text/plain'},
                                  pprint.pformat(server.sources))

class JSONStatusClient(HTTPEventHandler):

    def __init__(self, server, sock, address, request_parser):
        sources_dict = {}
        total_clients_number = 0
        for path, sources in server.sources.items():
            sources_dict[path] = {}
            for source, source_dict in sources.items():
                source_address = '%s:%s' % source.address
                sources_dict[path][source_address] = {}
                for fd, client in source_dict['clients'].items():
                    sources_dict[path][source_address][fd] = '%s:%s' % client.address
                    total_clients_number += 1

        status_dict = {
            'total_clients_number': total_clients_number,
            'pid': os.getpid(),
            'sources': sources_dict,
            }

        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  200, b'OK', {b'Content-Type': 'application/json'},
                                  json.dumps(status_dict, indent = 4) + '\n')

class StreamClient(HTTPEventHandler):

    def __init__(self, server, source, sock, address, request_parser, content_type):
        HTTPEventHandler.__init__(self, server, sock, address, request_parser,
                                  200, b'OK', {b'Content-Length': None,
                                               b'Content-Type': content_type})
        self.source = source

    def add_packet(self, packet):
        self.output_buffer.add_buffer(packet)

    def close(self):
        self.server.remove_client(self)
        HTTPEventHandler.close(self)

    def flush(self):
        HTTPEventHandler.flush(self)
        if self.output_buffer.ready:
            # De-activate handler to avoid unnecessary notifications
            self.server.loop.register(self, 0)

    def handle_event(self, eventmask):
        if eventmask & looping.POLLOUT:
            self.flush()
        elif eventmask & (looping.POLLERR | looping.POLLHUP):
            # Error / Hangup, client probably closed connection
            self.close()
        else:
            self.server.logger.error('%s: unexpected eventmask %d (%s)', self, eventmask, event_mask_str(eventmask))
