# -*- coding: utf-8 -*-

import os
try:
    import json
except ImportError:
    import simplejson as json
import pprint
from savate.helpers import HTTPEventHandler, HTTPResponse


class BaseStatusClient(object):

    def __init__(self, server, server_config, **config_dict):
        self.server = server
        self.server_config = server_config
        self.config = config_dict

    def get_status(self, sock, address, request_parser):
        raise NotImplemented('Implement in subclass')


class SimpleStatusClient(BaseStatusClient):

    def get_status(self, sock, address, request_parser):
        return HTTPEventHandler(self.server, sock, address, request_parser,
                                HTTPResponse(200, b'OK', {b'Content-Type': 'text/plain'},
                                pprint.pformat(self.server.sources)))


class JSONStatusClient(BaseStatusClient):

    def get_status(self, sock, address, request_parser):
        sources_dict = {}
        total_clients_number = 0
        for path, sources in self.server.sources.items():
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

        return HTTPEventHandler(self.server, sock, address, request_parser,
                                HTTPResponse(200, b'OK', {b'Content-Type': 'application/json'},
                                json.dumps(status_dict, indent = 4) + '\n'))


class StaticFileStatusClient(BaseStatusClient):

    def __init__(self, server, server_config, **config_dict):
        BaseStatusClient.__init__(self, server, server_config, **config_dict)
        self.static_filename = config_dict['static_file']

    def get_status(self, sock, address, request_parser):
        try:
            with open(self.static_filename) as static_fileobj:
                status_body = static_fileobj.read()
            return HTTPEventHandler(self.server, sock, address, request_parser,
                                    HTTPResponse(200, b'OK', {b'Content-Type': 'application/octet-stream'},
                                    status_body))
        except IOError, exc:
            self.server.logger.exception('Error when trying to serve static status file %s:',
                                         self.static_filename)
            return HTTPEventHandler(self.server, sock, address, request_parser,
                                    HTTPResponse(500, b'Internal Server Error', {b'Content-Type': 'text/plain'},
                                    'Failed to open static status file\n'))
