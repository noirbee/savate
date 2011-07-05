# -*- coding: utf-8 -*-

import errno
import urlparse
import socket
import struct
import cyhttp11
from savate import looping
from savate import sources
from savate import helpers
from savate.helpers import HTTPError, HTTPParseError
from savate.sources import MPEGTSSource
from savate import buffer_event

class Relay(looping.BaseIOEventHandler):

    def __init__(self, server, url, path, addr_info = None):
        self.server = server
        self.url = url
        self.parsed_url = urlparse.urlparse(url)
        self.path = path
        self.addr_info = addr_info

    def close(self):
        self.server.check_for_relay_restart(self)
        looping.BaseIOEventHandler.close(self)

class UDPRelay(Relay):

    def __init__(self, server, url, path, addr_info = None):
        Relay.__init__(self, server, url, path, addr_info)

        # UDP, possibly multicast input
        udp_address = (self.parsed_url.hostname, self.parsed_url.port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(udp_address)
        self.sock.setblocking(0)
        if self.parsed_url.scheme == 'multicast':
            multicast_request = struct.pack('=4sl', socket.inet_aton(self.parsed_url.hostname), socket.INADDR_ANY)
            self.sock.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, multicast_request)
            # The socket is now multicast ready

        # FIXME: we're assuming an MPEG-TS source
        udp_source = MPEGTSSource(server, self.sock, udp_address, b'video/MP2T', None, path)
        self.server.add_source(path, udp_source)


class HTTPRelay(Relay):

    REQUEST_METHOD = b'GET'
    HTTP_VERSION = b'HTTP/1.1'
    RESPONSE_MAX_SIZE = 4096

    def __init__(self, server, url, path, addr_info = None):
        Relay.__init__(self, server, url, path, addr_info)

        if addr_info:
            self.sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
            self.host_address = addr_info[4][0]
            self.host_port = addr_info[4][1]
        else:
            self.sock = socket.socket()
            self.host_address = self.parsed_url.hostname
            self.host_port = self.parsed_url.port

        self.sock.setblocking(0)
        error = self.sock.connect_ex((self.host_address,
                                      self.host_port))
        if error != errno.EINPROGRESS:
            raise socket.error(error, errno.errorcode[error])
        self.handle_event = self.handle_connect
        self.server.loop.register(self, looping.POLLOUT)

    def handle_connect(self, eventmask):
        if eventmask & looping.POLLOUT:
            error = self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if error:
                raise socket.error(error, errno.errorcode[error])
            self.address = self.sock.getpeername()
            # We're connected, prepare to send our request
            _req = self._build_request()
            self.output_buffer = buffer_event.BufferOutputHandler(self.sock,
                                                                  (_req,))
            self.handle_event = self.handle_request
            # Immediately try to send some data
            self.handle_event(eventmask)

    def _build_request(self):
        # FIXME: URL encoding for the request path
        # FIXME: params, query and fragments are discarded
        request_line = b'%s %s %s' % (self.REQUEST_METHOD, self.parsed_url.path,
                                     self.HTTP_VERSION)
        # FIXME: should we send some more headers ?
        headers_lines = helpers.build_http_headers({b'Host': self.parsed_url.hostname}, b'')
        # FIXME: should we send a body ?
        return bytes(b'\r\n'.join([request_line, headers_lines, b'']))

    def handle_request(self, eventmask):
        if eventmask & looping.POLLOUT:
            self.output_buffer.flush()
            if self.output_buffer.empty():
                # Request sent, switch to HTTP client parsing mode
                self.server.loop.register(self, looping.POLLIN)
                self.response_buffer = b''
                self.response_size = 0
                self.response_parser = cyhttp11.HTTPClientParser()
                self.handle_event = self.handle_response

    def handle_response(self, eventmask):
        if eventmask & looping.POLLIN:
            # FIXME: this is basically a c/c from server.py's
            # HTTPClient's handle_read
            while True:
                tmp_buffer = helpers.handle_eagain(self.sock.recv,
                                                   self.RESPONSE_MAX_SIZE - self.response_size)
                if tmp_buffer == None:
                    # EAGAIN, we'll come back later
                    break
                elif tmp_buffer == b'':
                    raise HTTPError('Unexpected end of stream from %s, %s' %
                                    (self.url,
                                    (self.sock, self.address)))
                self.response_buffer = self.response_buffer + tmp_buffer
                self.response_size += len(tmp_buffer)
                self.response_parser.execute(self.response_buffer)
                if self.response_parser.has_error():
                    raise HTTPParseError('Invalid HTTP response from %s, %s' %
                                         (self.sock, self.address))
                elif self.response_parser.is_finished():
                    # Transform this into the appropriate handler
                    self.transform_response()
                    break
                elif self.response_size >= self.RESPONSE_MAX_SIZE:
                    raise HTTPParseError('Oversized HTTP response from %s, %s' %
                                         (self.sock, self.address))

    def transform_response(self):
        if self.response_parser.status_code not in (200,):
            raise HTTPError('Unexpected response %d %s from %s, %s' %
                            (self.response_parser.status_code,
                             self.response_parser.reason_phrase,
                             self.url,
                             (self.sock, self.address)))
        content_type = self.response_parser.headers.get('Content-Type',
                                                        'application/octet-stream')
        # FIXME: similar code is present in server.py
        loop = self.server.loop
        if content_type in sources.sources_mapping:
            self.server.logger.info('New source for %s: %s', self.path, self.address)
            source = sources.sources_mapping[content_type](self.server,
                                                           self.sock,
                                                           self.address,
                                                           content_type,
                                                           self.response_parser,
                                                           self.path)
            self.server.add_source(self.path, source)
        else:
            self.server.logger.warning('Unrecognized Content-Type %s', content_type)
            loop.register(helpers.HTTPEventHandler(self.server,
                                                   self.sock,
                                                   self.address,
                                                   self.response_parser,
                                                   501,
                                                   b'Not Implemented'),
                          looping.POLLOUT)
