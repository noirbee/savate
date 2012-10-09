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
        self.server.remove_inactivity_timeout(self)
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

        self.server.request_in(self.request_parser, self.sock)

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
                return

        path = self.request_parser.request_path

        response = None

        if self.request_parser.request_method in [b'PUT', b'SOURCE', b'POST']:
            self.server.register_source(sources.find_source(
                self.server, self.sock, self.address, self.request_parser, path))
        elif self.request_parser.request_method in [b'GET', b'HEAD']:
            # New client

            # Is our client asking for status ?
            if path in self.server.status_handlers:
                # FIXME: should we handle HEAD requests ?
                if self.request_parser.request_method not in [b'GET']:
                    response = HTTPResponse(405, b'Method Not Allowed')
                else:
                    loop.register(self.server.status_handlers[path].get_status(self.sock,
                                                                               self.address,
                                                                               self.request_parser),
                                  looping.POLLOUT)
            else:
                # New client for one of our sources
                if self.server.sources.get(path, []):
                    # Used by some clients to know the stream type
                    # before attempting playout
                    if self.request_parser.request_method in [b'HEAD']:
                        source = self.server.sources[path].keys()[0]
                        response = HTTPResponse(200, b'OK', {b'Content-Type': source.content_type,
                                                             b'Content-Length': None,
                                                             b'Connection': b'close'})
                    # Check for server clients limit
                    elif self.server.clients_limit is not None and (
                        self.server.clients_limit == self.server.clients_connected):
                        response = HTTPResponse(503, b'Cannot handle response.'
                                                b' Too many clients.')
                    else:
                        # FIXME: proper source selection
                        source = random.choice(self.server.sources[path].keys())
                        new_client = clients.find_client(self.server,
                                                         source,
                                                         self.sock,
                                                         self.address,
                                                         self.request_parser)
                        # FIXME: this call may actually need to instatiate
                        # the client itself (e.g. if the source needs some
                        # dedicated code in its clients)
                        source.new_client(new_client)
                        # FIXME: see above wrt to proper source selection
                        self.server.sources[path][source]['clients'][new_client.fileno()] = new_client
                        self.server.clients_connected += 1
                        loop.register(new_client,
                                      looping.POLLOUT)
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
        self.keepalived = collections.defaultdict(list)
        self.sources = {}
        self.relays = {}
        self.relays_to_restart = collections.deque()
        self.auth_handlers = []
        self.status_handlers = {}
        self.statistics_handlers = []
        self.state = self.STATE_RUNNING
        self.reloading = False
        self.timeouts = None
        self.io_timeouts = None
        # keep a counter for limit on *streaming* clients
        self.clients_connected = 0

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
            self.io_timeouts = timeouts.IOTimeout(self.timeouts)

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            try:
                helpers.loop_for_eagain(self.handle_new_incoming)
            except IOError as exc:
                if exc.errno in (errno.EMFILE, errno.ENFILE):
                    # Too many open files
                    self.logger.error('Cannot accept, too many open files')
                    # Shutdown the socket to try an clear the backlog,
                    # which should disconnect the client; then
                    # re-listen() on it immediately
                    self.sock.shutdown(socket.SHUT_RD)
                    self.sock.listen(self.BACKLOG)
                else:
                    raise

    def reset_inactivity_timeout(self, handler):
        self.io_timeouts.reset_timeout(
            handler,
            int(self.loop.now()) + self.INACTIVITY_TIMEOUT,
        )

    def remove_inactivity_timeout(self, handler):
        self.io_timeouts.remove_timeout(handler)

    def handle_new_incoming(self):
        client_socket, client_address = self.sock.accept()
        self.logger.info('New client %s, %s', client_socket, client_address)
        new_handler = HTTPRequest(self, client_socket, client_address)
        self.reset_inactivity_timeout(new_handler)

        self.loop.register(new_handler, looping.POLLIN)

    def configure(self):
        self.config.configure()

    def request_in(self, request_parser, sock):
        for stat in self.statistics_handlers:
            stat.request_in(request_parser, sock)

    def request_out(self, request_parser, sock, address, size=0, duration=0,
                    status_code=200):
        for stat in self.statistics_handlers:
            stat.request_out(request_parser, sock, address, size, duration,
                             status_code)

    def add_relay(self, url, path, address_info = None, burst_size = None,
                  on_demand = False, keepalive = False):
        if urlparse.urlparse(url).scheme in ('udp', 'multicast'):
            tmp_relay = relay.UDPRelay(self, url, path, address_info,
                                       burst_size)
        else:
            tmp_relay = relay.HTTPRelay(self, url, path, address_info,
                                        burst_size, on_demand, keepalive)
        self.relays[tmp_relay.sock] = tmp_relay

    def add_auth_handler(self, handler):
        self.auth_handlers.append(handler)

    def add_status_handler(self, path, handler):
        self.status_handlers[path] = handler

    def add_stats_handler(self, handler):
        self.statistics_handlers.append(handler)

    def add_source(self, path, sock, address, request_parser,
                   burst_size = None):

        source = sources.find_source(self, sock, address, request_parser, path,
                                     burst_size)
        self.register_source(source)

    def register_source(self, source):
        self.logger.info('New source (%s) for %s: %s',
                         source.__class__.__name__, source.path, source.address)
        self.sources.setdefault(source.path, {})[source] = {'source': source,
                                                            'clients': {}}
        self.reset_inactivity_timeout(source)
        self.loop.register(source, looping.POLLIN)

        # check if there are listeners waiting
        if self.keepalived[source.path]:
            # cancel timeout
            self.timeouts.remove_timeout(source.path)
            for client in self.keepalived[source.path]:
                client.source = source
                self.sources[source.path][source]['clients'][client.fileno()] = client

            del self.keepalived[source.path]

    def update_activity(self, handler):
        self.reset_inactivity_timeout(handler)

    def check_for_relay_restart(self, handler):
        # If this is one of our relays, mark it for restart
        if handler.sock in self.relays:
            # It will be restarted in one second from now
            # FIXME: use real timers
            self.relays_to_restart.append((self.loop.now() + self.RESTART_DELAY,
                                           self.relays.pop(handler.sock)))

    def remove_source(self, source):
        # De-activate the timeout handling for this source
        self.remove_inactivity_timeout(source)
        # Remove on demand closing timeout
        self.timeouts.remove_timeout(source)

        keepalive = source.keepalive

        # FIXME: client shutdown
        if len(self.sources[source.path]) > 1:
            # There is at least one other source for this path,
            # migrate the clients to it
            tmp_source = self.sources[source.path].pop(source)
            # Simple even distribution amongst the remaining sources
            for client, new_source in itertools.izip(tmp_source['clients'].itervalues(),
                                                     itertools.cycle(self.sources[source.path].keys())):
                client.source = new_source
                self.sources[source.path][new_source]['clients'][client.fileno()] = client
                # if source is on demand and not running, then start it
                new_source.on_demand_activate()
        else:
            for client in self.sources[source.path][source]['clients'].values():
                if keepalive:
                    # try to keep the clients
                    client.source = None
                    # we don't clear client buffer because player can't
                    # resynchronise on the stream, this result in a mix of old
                    # frames and new ones when the source reconnects which can
                    # be weird
                    self.keepalived[source.path].append(client)
                else:
                    client.close()
            if keepalive:
                # timeout n seconds
                def my_closure():
                    # close clients
                    self.logger.error('Keepalive client trashed')
                    for client in self.keepalived[source.path]:
                        # in case client was disconnected already
                        if not client.closed:
                            client.close()
                    del self.keepalived[source.path]

                self.timeouts.reset_timeout(
                    source.path,
                    self.loop.now() + keepalive,
                    my_closure,
                )
            del self.sources[source.path]
        self.loop.unregister(source)
        self.check_for_relay_restart(source)

    def remove_client(self, client):
        self.clients_connected -= 1
        source = client.source
        self.loop.unregister(client)
        if source is None:
            return

        del self.sources[source.path][source]['clients'][client.fileno()]
        # FIXME: what to do with this one ?
        self.logger.info(
            'Dropping client for path %s, %s',
            source.path,
            client.address,
        )

    def all_clients(self):
        return itertools.chain.from_iterable(source_dict['clients'].itervalues()
                                             for source in self.sources.itervalues()
                                             for source_dict in source.itervalues()
                                             )

    def publish_packet(self, source, packet):
        for client in self.sources[source.path][source]['clients'].values():
            client.add_packet(packet)

    def serve_forever(self):
        while (self.state == self.STATE_RUNNING or
               (self.state == self.STATE_SHUTTING_DOWN and any(self.all_clients()))):
            self.loop.once(self.LOOP_TIMEOUT)

            while (self.relays_to_restart and
                   self.relays_to_restart[0][0] < self.loop.now()):
                self.logger.info('Restarting relay %s', self.relays_to_restart[0][1])
                tmp_relay = self.relays_to_restart.popleft()[1]
                self.add_relay(tmp_relay.url, tmp_relay.path,
                               tmp_relay.addr_info, tmp_relay.burst_size,
                               tmp_relay.on_demand, tmp_relay.keepalive)

            if self.reloading:
                self.reloading = False
                with open(self.config_file) as conf_file:
                    try:
                        config_dict = json.load(conf_file)
                        self.config.reconfigure(config_dict)
                    except (ValueError, configuration.BadConfig):
                        self.logger.exception('Bad config file:')

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
