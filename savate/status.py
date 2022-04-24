import os
import json
import pprint
import socket
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from cyhttp11 import HTTPParser

from savate.helpers import HTTPEventHandler, HTTPResponse
from savate.sources import StreamSource
if TYPE_CHECKING:
    from savate.server import TCPServer


class BaseStatusClient(ABC):

    def __init__(self, server: "TCPServer", server_config: dict[str, Any], **config_dict: Any) -> None:
        self.server = server
        self.server_config = server_config
        self.config = config_dict

    @abstractmethod
    def get_status(self, sock: socket.socket, address: tuple[str, int], request_parser: HTTPParser) -> HTTPEventHandler:
        ...


class SimpleStatusClient(BaseStatusClient):

    def get_status(self, sock: socket.socket, address: tuple[str, int], request_parser: HTTPParser) -> HTTPEventHandler:
        return HTTPEventHandler(self.server, sock, address, request_parser,
                                HTTPResponse(200, b'OK', {b'Content-Type': b'text/plain'},
                                             bytes(pprint.pformat(self.server.sources), "ascii")))


class JSONStatusClient(BaseStatusClient):

    def get_status(self, sock: socket.socket, address: tuple[str, int], request_parser: HTTPParser) -> HTTPEventHandler:
        sources_dict: dict[str, dict[str, dict[int, str]]] = {}
        total_clients_number = 0

        queue_sizes = []

        for path, sources in self.server.sources.items():
            sources_dict[path] = {}
            for source, source_dict in list(sources.items()):
                source_address = '%s:%s (%s)' % (source.address[0],
                                                 source.address[1], id(source))
                sources_dict[path][source_address] = {}
                for fd, client in list(source_dict['clients'].items()):
                    sources_dict[path][source_address][fd] = '%s:%s' % client.address
                    total_clients_number += 1
                    queue_sizes.append(sum(len(elt) for elt in client.output_buffer.buffer_queue))

        queue_sizes.sort()
        if not queue_sizes:
            queue_sizes = [-1]
        status_dict = {
            'total_clients_number': total_clients_number,
            'pid': os.getpid(),
            'max_buffer_queue_size': queue_sizes[-1],
            'min_buffer_queue_size': queue_sizes[0],
            'median_buffer_queue_size': queue_sizes[total_clients_number // 2],
            'average_buffer_queue_size': sum(queue_sizes) / len(queue_sizes),
            'sources': sources_dict,
            }

        return HTTPEventHandler(self.server, sock, address, request_parser,
                                HTTPResponse(200, b'OK', {b'Content-Type': b'application/json'},
                                             bytes(json.dumps(status_dict, indent = 4) + '\n', "utf-8")))


class StaticFileStatusClient(BaseStatusClient):

    def __init__(self, server: "TCPServer", server_config: dict[str, Any], **config_dict: Any) -> None:
        super().__init__(server, server_config, **config_dict)
        self.static_filename = config_dict['static_file']

    def get_status(self, sock: socket.socket, address: tuple[str, int], request_parser: HTTPParser) -> HTTPEventHandler:
        try:
            with open(self.static_filename, "rb") as static_fileobj:
                status_body = static_fileobj.read()
            return HTTPEventHandler(self.server, sock, address, request_parser,
                                    HTTPResponse(200, b'OK', {b'Content-Type': b'application/octet-stream'},
                                    status_body))
        except IOError as exc:
            self.server.logger.exception('Error when trying to serve static status file %s:',
                                         self.static_filename)
            return HTTPEventHandler(self.server, sock, address, request_parser,
                                    HTTPResponse(500, b'Internal Server Error', {b'Content-Type': b'text/plain'},
                                    b'Failed to open static status file\n'))
