# -*- coding: utf-8 -*-

import socket
import logging
import collections
import random
import datetime
import re
import cyhttp11
from savate import looping
from savate import helpers
from savate.helpers import HTTPError, HTTPParseError
from savate import clients
from savate import sources
from savate import relay

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
                break
            elif self.request_size >= self.REQUEST_MAX_SIZE:
                raise HTTPParseError('Oversized HTTP request from %s, %s' %
                                     (self.sock, self.address))

    def transform_request(self):
        loop = self.server.loop
        # FIXME: should we shutdown() read or write depending on what
        # we do here ? (i.e. SHUT_RD for GETs, SHUT_WD for sources)

        self.server.logger.info('%s:%s %s %s %s, request headers: %s',
                                self.address[0], self.address[1],
                                self.request_parser.request_method,
                                self.request_parser.request_path,
                                self.request_parser.http_version,
                                self.request_parser.headers)

        # Squash any consecutive / into one
        self.request_parser.request_path = re.sub('//+', '/',
                                                  self.request_parser.request_path)
        path = self.request_parser.request_path

        if self.request_parser.request_method in [b'PUT', b'SOURCE', b'POST']:
            # New source
            content_type = self.request_parser.headers.get('Content-Type',
                                                           'application/octet-stream')
            if content_type in sources.sources_mapping:
                self.server.logger.info('New source for %s: %s', path, self.address)
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
                self.server.logger.warning('Unrecognized Content-Type %s', content_type)
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

            elif path in [b'/status.json']:
                # Deliver server status, JSON version
                loop.register(clients.JSONStatusClient(self.server,
                                                       self.sock,
                                                       self.address,
                                                       self.request_parser),
                              looping.POLLOUT)

            else:
                # New client for one of our sources
                if self.server.sources.get(path, []):
                    # FIXME: proper source selection
                    source = random.choice(self.server.sources[path].keys())
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
                                  looping.POLLOUT)
                else:
                    # Stream does not exist
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

class InactivityTimeout(Exception):
    pass

class TCPServer(looping.BaseIOEventHandler):

    BACKLOG = 1000

    LOOP_TIMEOUT = 0.5

    # Maximum I/O inactivity timeout, in milliseconds
    INACTIVITY_TIMEOUT = 10 * 1000

    def __init__(self, address, logger = None):
        self.address = address
        self.logger = logger or logging.getLogger('savate')
        self.create_socket(address)
        self.sources = {}
        self.relays = {}
        self.relays_to_restart = collections.deque()

    def create_loop(self):
        self.loop = looping.IOLoop(self.logger)
        self.loop.register(self, looping.POLLIN)

    def create_socket(self, address):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(address)
        self.sock.listen(self.BACKLOG)
        self.sock.setblocking(0)

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            helpers.loop_for_eagain(self.handle_new_incoming)

    def handle_new_incoming(self):
        client_socket, client_address = self.sock.accept()
        self.logger.info('New client %s, %s', client_socket, client_address)
        self.loop.register(HTTPClient(self, client_socket, client_address), looping.POLLIN)

    def add_relay(self, *relay_args):
        tmp_relay = relay.HTTPRelay(*relay_args)
        self.relays[tmp_relay.sock] = relay_args
        self.loop.register(tmp_relay, looping.POLLOUT)

    def check_for_timeout(self, last_activity):
        if ((datetime.datetime.now() - last_activity) >
            datetime.timedelta(milliseconds = self.INACTIVITY_TIMEOUT)):
            # Client/source timeout
            raise InactivityTimeout('Timeout: %d milliseconds without I/O' %
                                    self.INACTIVITY_TIMEOUT)

    def check_for_relay_restart(self, handler):
        # If this is one of our relays, mark it for restart
        if handler.sock in self.relays:
            self.relays_to_restart.append(self.relays.pop(handler.sock))

    def remove_source(self, source):
        # FIXME: client shutdown
        for client in self.sources[source.path][source]['clients'].values():
            client.close()
        self.loop.unregister(source)
        del self.sources[source.path][source]
        self.check_for_relay_restart(source)

    def remove_client(self, client):
        source = client.source
        self.logger.info('Dropping client for path %s, %s', source.path,
                         client.address)
        self.loop.unregister(client)
        del self.sources[source.path][source]['clients'][client.fileno()]

    def publish_packet(self, source, packet):
        for client in self.sources[source.path][source]['clients'].values():
            client.add_packet(packet)
            self.loop.inject_event(client.fileno(), looping.POLLOUT)

    def serve_forever(self):
        while True:
            self.loop.once(self.LOOP_TIMEOUT)
            while self.relays_to_restart:
                self.logger.info('Restarting relay %s', self.relays_to_restart[0])
                self.add_relay(*self.relays_to_restart.popleft())
