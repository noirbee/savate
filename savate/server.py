# -*- coding: utf-8 -*-

import socket
from datetime import datetime
import logging
import collections
import random
import re
import itertools
import errno
import urlparse
try:
    import json
except ImportError:
    import simplejson as json

import cyhttp11

from savate import looping
from savate import configuration
from savate import helpers
from savate.helpers import HTTPError, HTTPParseError, HTTPResponse, find_signal_str
from savate import clients
from savate import sources
from savate import relay
from savate import timeouts


class HTTPRequest(looping.BaseIOEventHandler):

    REQUEST_MAX_SIZE = 4096

    def __init__(self, server, sock, address):
        self.server = server
        self.sock = sock
        self.sock.setblocking(0)
        self.address = address
        self.request_size = 0
        self.request_buffer = b''
        self.request_parser = cyhttp11.HTTPParser()

    def close(self):
        self.server.timeouts.remove_timeout(self)
        self.server.loop.unregister(self)
        looping.BaseIOEventHandler.close(self)

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

        self.server.logger.debug('%s:%s %s %s %s, request headers: %s',
                                self.address[0], self.address[1],
                                self.request_parser.request_method,
                                self.request_parser.request_path,
                                self.request_parser.http_version,
                                self.request_parser.headers)

        # Squash any consecutive / into one
        self.request_parser.request_path = re.sub('//+', '/',
                                                  self.request_parser.request_path)
        # Authorization
        for auth_handler in self.server.auth_handlers:
            auth_result = auth_handler.authorize(self.address, self.request_parser)
            if auth_result is None:
                continue
            elif not isinstance(auth_result, HTTPResponse):
                # Wrong response from auth handler
                raise RuntimeError('Wrong response from authorization handler %s' % auth_handler)
            elif auth_result.status == 200:
                # Request authorized
                break
            else:
                # Access denied
                loop.register(helpers.HTTPEventHandler(self.server,
                                                       self.sock,
                                                       self.address,
                                                       self.request_parser,
                                                       auth_result),
                              looping.POLLOUT)
                self.log_request(auth_result.status)
                return

        path = self.request_parser.request_path

        response = None

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
                self.server.add_source(path, source)
            else:
                self.server.logger.warning('Unrecognized Content-Type %s', content_type)
                response = HTTPResponse(501, b'Not Implemented')
        elif self.request_parser.request_method in [b'GET']:
            # New client

            # Is our client asking for status ?
            if path in self.server.status_handlers:
                loop.register(self.server.status_handlers[path].get_status(self.sock,
                                                                           self.address,
                                                                           self.request_parser),
                              looping.POLLOUT)
                self.log_request(200)
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
                    self.log_request(200)
                else:
                    # Stream does not exist
                    response = HTTPResponse(404, b'Stream Not Found')

        else:
            # Unknown HTTP request method
            response = HTTPResponse(405, b'Method Not Allowed')

        if response is not None:
            loop.register(helpers.HTTPEventHandler(self.server,
                                                   self.sock,
                                                   self.address,
                                                   self.request_parser,
                                                   response),
                          looping.POLLOUT)
            self.log_request(response.status)

    def log_request(self, status_code):
        # Log as Apache's combined log format
        user_agent = self.request_parser.headers.get('User-Agent', '-')
        referer = self.request_parser.headers.get('Referer', '-')
        self.server.logger.info('%s - %s [%s] "%s %s %s" %d %s "%s" "%s"',
                                self.address[0],
                                '-', # FIXME: replace by the username
                                datetime.fromtimestamp(self.server.loop.now()).strftime("%d/%b/%Y:%H:%M:%S +0000"), # FIXME: make this timezone aware
                                self.request_parser.request_method,
                                self.request_parser.request_path,
                                self.request_parser.http_version,
                                status_code,
                                '-', # FIXME: replace by the size of the request
                                referer,
                                user_agent)

class InactivityTimeout(Exception):
    pass


class TCPServer(looping.BaseIOEventHandler):

    BACKLOG = 1000

    LOOP_TIMEOUT = 0.5

    # Maximum I/O inactivity timeout, in seconds
    INACTIVITY_TIMEOUT = 10

    RESTART_DELAY = 1

    STATE_RUNNING = 'RUNNING'
    STATE_STOPPED = 'STOPPED'
    STATE_SHUTTING_DOWN = 'SHUTTING_DOWN'

    def __init__(self, address, config_file, logger = None):
        self.address = address
        self.config_file = config_file
        with open(self.config_file) as conf_file:
            self.config = configuration.ServerConfiguration(self, json.load(conf_file))
        self.logger = logger or logging.getLogger('savate')
        self.sources = {}
        self.relays = {}
        self.relays_to_restart = collections.deque()
        self.auth_handlers = []
        self.status_handlers = {}
        self.state = self.STATE_RUNNING
        self.reloading = False
        self.timeouts = None

    def create_loop(self):
        self.loop = looping.IOLoop(self.logger)
        self.loop.register(self, looping.POLLIN)
        # Our timeout handler
        self.loop.register(self.timeouts, looping.POLLIN)

    def create_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(self.address)
        self.sock.listen(self.BACKLOG)
        self.sock.setblocking(0)

        # The Timeouts object uses a file descriptor, so we must
        # initialise here to avoid having it closed by daemonisation
        if not self.timeouts:
            self.timeouts = timeouts.Timeouts(self)

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            try:
                helpers.loop_for_eagain(self.handle_new_incoming)
            except IOError as exc:
                if exc.errno in (errno.EMFILE, errno.ENFILE):
                    # Too many open files
                    self.logger.error('Cannot accept, too many open files')
                    # Try to close() and re-open our listening socket,
                    # since there is no other way to clear the backlog
                    # FIXME: remove from poller object, and try to
                    # re-add it later ? Do not try to accept() once
                    # we've reached the open file descriptors / max
                    # clients limit ?
                    self.loop.unregister(self)
                    self.close()
                    self.create_socket()
                    self.loop.register(self, looping.POLLIN)
                else:
                    raise

    def handle_new_incoming(self):
        client_socket, client_address = self.sock.accept()
        self.logger.info('New client %s, %s', client_socket, client_address)
        new_handler = HTTPRequest(self, client_socket, client_address)
        self.timeouts.update_timeout(new_handler, int(self.loop.now()) + self.INACTIVITY_TIMEOUT)
        self.loop.register(new_handler, looping.POLLIN)

    def configure(self):
        self.config.configure()

    def add_relay(self, url, path, address_info = None):
        if urlparse.urlparse(url).scheme in ('udp', 'multicast'):
            tmp_relay = relay.UDPRelay(self, url, path, address_info)
        else:
            tmp_relay = relay.HTTPRelay(self, url, path, address_info)
        self.relays[tmp_relay.sock] = tmp_relay

    def add_auth_handler(self, handler):
        self.auth_handlers.append(handler)

    def add_status_handler(self, path, handler):
        self.status_handlers[path] = handler

    def add_source(self, path, source):
        self.sources.setdefault(path, {})[source] = {'source': source,
                                                     'clients': {}}
        self.timeouts.update_timeout(source, int(self.loop.now()) + self.INACTIVITY_TIMEOUT)
        self.loop.register(source, looping.POLLIN)

    def update_activity(self, handler):
        self.timeouts.update_timeout(handler, int(self.loop.now()) + self.INACTIVITY_TIMEOUT)

    def check_for_relay_restart(self, handler):
        # If this is one of our relays, mark it for restart
        if handler.sock in self.relays:
            # It will be restarted in one second from now
            # FIXME: use real timers
            self.relays_to_restart.append((self.loop.now() + self.RESTART_DELAY,
                                           self.relays.pop(handler.sock)))

    def remove_source(self, source):
        # De-activate the timeout handling for this source
        self.timeouts.remove_timeout(source)
        # FIXME: client shutdown
        if len(self.sources[source.path]) > 1:
            # There is at least one other source for this path,
            # migrate the clients to it
            tmp_source = self.sources[source.path].pop(source)
            # Simple even distribution amongst the remaining sources
            for client, new_source in itertools.izip(tmp_source['clients'].values(),
                                                     itertools.cycle(self.sources[source.path].keys())):
                client.source = new_source
                self.sources[source.path][new_source]['clients'][client.fileno()] = client
        else:
            for client in self.sources[source.path][source]['clients'].values():
                client.close()
            del self.sources[source.path]
        self.loop.unregister(source)
        self.check_for_relay_restart(source)

    def remove_client(self, client):
        # De-activate the timeout handling for this client
        self.timeouts.remove_timeout(client)

        source = client.source
        self.logger.info('Dropping client for path %s, %s', source.path,
                         client.address)
        self.loop.unregister(client)
        del self.sources[source.path][source]['clients'][client.fileno()]

    def all_clients(self):
        return itertools.chain.from_iterable(source_dict['clients'].itervalues()
                                             for source in self.sources.itervalues()
                                             for source_dict in source.itervalues()
                                             )

    def publish_packet(self, source, packet):
        for client in self.sources[source.path][source]['clients'].values():
            client.add_packet(packet)
            self.loop.inject_event(client.fileno(), looping.POLLOUT)

    def serve_forever(self):
        while (self.state == self.STATE_RUNNING or
               (self.state == self.STATE_SHUTTING_DOWN and any(self.all_clients()))):
            self.loop.once(self.LOOP_TIMEOUT)

            while (self.relays_to_restart and
                   self.relays_to_restart[0][0] < self.loop.now()):
                self.logger.info('Restarting relay %s', self.relays_to_restart[0][1])
                tmp_relay = self.relays_to_restart.popleft()[1]
                self.add_relay(tmp_relay.url, tmp_relay.path, tmp_relay.addr_info)

            if self.reloading:
                self.reloading = False
                with open(self.config_file) as conf_file:
                    self.config.reconfigure(json.load(conf_file))

        # FIXME: we should probably close() every source/client and
        # the server instance itself
        self.logger.info('Shutting down')

    def stop(self, signum, _frame):
        self.logger.info('Received signal %s, stopping main loop', find_signal_str(signum))
        self.state = self.STATE_STOPPED

    def reload(self, signum, _frame):
        self.logger.info('Received signal %s, reloading configuration', find_signal_str(signum))
        self.reloading = True

    def graceful_stop(self, signum, _frame):
        self.logger.info('Received signal %s, performing graceful stop', find_signal_str(signum))
        # Close our accept() socket
        self.loop.unregister(self)
        self.close()
        self.state = self.STATE_SHUTTING_DOWN
