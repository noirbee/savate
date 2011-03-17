# -*- coding: utf-8 -*-

import socket
import looping
import helpers
import clients
import sources
import collections
import cyhttp11

class HTTPError(Exception):
    pass
class HTTPParseError(HTTPError):
    pass

class HTTPClient(looping.BaseIOEventHandler):

    REQUEST_MAX_SIZE = 4096

    def __init__(self, server, sock, address):
        self.server = server
        self.sock = sock
        self.sock.setblocking(0)
        self.address = address
        self.request_size = 0
        self.request_buffer = b''
        self.request_parser = cyhttp11.HTTPParser()

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            self.handle_read()

    def handle_read(self):
        while True:
            tmp_buffer = helpers.handle_eagain(self.sock.recv,
                                               self.REQUEST_MAX_SIZE - self.request_size)
            if tmp_buffer == None:
                # EAGAIN, we'll come back later
                break
            elif tmp_buffer == b'':
                raise HTTPError('Unexpected end of stream from %s, %s,' %
                                (self.sock, self.address))
            self.request_buffer = self.request_buffer + tmp_buffer
            self.request_size += len(tmp_buffer)
        self.request_parser.execute(self.request_buffer)
        if self.request_parser.has_error():
            raise HTTPParseError('Invalid HTTP request from %s, %s' %
                                 (self.sock, self.address))
        elif self.request_parser.is_finished():
            # Transform this into the appropriate handler
            self.transform_request()
        elif self.request_size >= self.REQUEST_MAX_SIZE:
            raise HTTPParseError('Oversized HTTP request from %s, %s' %
                                 (self.sock, self.address))

    def transform_request(self):
        loop = self.server.loop
        # FIXME: should we shutdown() read or write depending on what
        # we do here ? (i.e. SHUT_RD for GETs, SHUT_WD for sources)

        self.server.log('Request headers: %s' % (self.request_parser.headers))

        path = self.request_parser.request_path

        if self.request_parser.request_method in [b'PUT', b'SOURCE', b'POST']:
            # New source
            content_type = self.request_parser.headers.get('Content-Type',
                                                           'application/octet-stream')
            if content_type in sources.sources_mapping:
                self.server.log('New source %s, %s' % (self.sock, self.address))
                source = sources.sources_mapping[content_type](self.server,
                                                               self.sock,
                                                               self.address,
                                                               content_type,
                                                               self.request_parser)
                self.server.sources.setdefault(
                    path,
                    {}
                    )[source] = {'source': source, 'clients': {}}
                loop.register(source,
                              looping.POLLIN)
            else:
                self.server.log('Unrecognized Content-Type %s' % (content_type))
                loop.register(helpers.HTTPEventHandler(self.server,
                                                       self.sock,
                                                       self.address,
                                                       self.request_parser,
                                                       501,
                                                       b'Not Implemented'),
                              looping.POLLOUT)
        elif self.request_parser.request_method in [b'GET']:
            # New client
            if path in [b'/status']:
                # Deliver server status
                loop.register(clients.StatusClient(self.server,
                                                   self.sock,
                                                   self.address,
                                                   self.request_parser),
                              looping.POLLOUT)

            else:
                # New client for one of our sources
                if self.server.sources.get(path, []):
                    # FIXME: proper source selection
                    source = self.server.sources[path].keys()[0]
                    new_client = clients.StreamClient(self.server,
                                                      source,
                                                      self.sock,
                                                      self.address,
                                                      self.request_parser,
                                                      source.content_type)
                    # FIXME: this call may actually need to instatiate
                    # the client itself (e.g. if the source needs some
                    # dedicated code in its clients)
                    source.new_client(new_client)
                    # FIXME: see above wrt to proper source selection
                    self.server.sources[path][source]['clients'][new_client.fileno()] = new_client
                    loop.register(new_client,
                                  looping.POLLOUT | looping.POLLET)
                else:
                    # Unknown HTTP request method
                    loop.register(helpers.HTTPEventHandler(self.server,
                                                           self.sock,
                                                           self.address,
                                                           self.request_parser,
                                                           404,
                                                           b'Stream Not Found'),
                                  looping.POLLOUT)

        else:
            # Unknown HTTP request method
            loop.register(helpers.HTTPEventHandler(self.server,
                                                   self.sock,
                                                   self.address,
                                                   self.request_parser,
                                                   405,
                                                   b'Method Not Allowed'),
                          looping.POLLOUT)


class TCPServer(looping.BaseIOEventHandler):

    BACKLOG = 1000

    LOOP_TIMEOUT = 0.5

    def __init__(self, address):
        self.address = address
        self.loop = looping.IOLoop()
        self.create_socket(address)
        self.loop.register(self, looping.POLLIN)
        self.sources = {}

    def create_socket(self, address):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(address)
        self.sock.listen(self.BACKLOG)
        self.sock.setblocking(0)

    def log(self, message, *args):
        print message % (args)

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            helpers.loop_for_eagain(self.handle_new_incoming)

    def handle_new_incoming(self):
        client_socket, client_address = self.sock.accept()
        self.log('New client %s, %s', client_socket, client_address)
        self.loop.register(HTTPClient(self, client_socket, client_address), looping.POLLIN)

    def remove_source(self, source):
        # FIXME: client shutdown
        for client in self.sources[source.path][source]['clients'].values():
            client.close()
        self.loop.unregister(source)
        del self.sources[source.path][source]

    def remove_client(self, client):
        self.log('Dropping client %s, %s', client.sock, client.address)
        self.loop.unregister(client)
        source = client.source
        del self.sources[source.path][source]['clients'][client.fileno()]

    def publish_packet(self, source, packet):
        for client in self.sources[source.path][source]['clients'].values():
            client.add_packet(packet)
            self.loop.inject_event(client.fileno(), looping.POLLOUT)

    def serve_forever(self):
        while True:
            self.loop.once(self.LOOP_TIMEOUT)

if __name__ == '__main__':

    server = TCPServer(('127.0.0.1', 5555))
    server.serve_forever()
