import errno
import urllib.parse
import socket
import struct
from typing import TYPE_CHECKING, Optional

import cyhttp11

from savate import looping
from savate import sources
from savate import helpers
from savate.helpers import AddrInfo, HTTPError, HTTPParseError
from savate.sources import MPEGTSSource
from savate import buffer_event

if TYPE_CHECKING:
    from savate.server import TCPServer


class Relay(looping.BaseIOEventHandler):
    def __init__(
        self,
        server: "TCPServer",
        url: str,
        path: str,
        addr_info: Optional[AddrInfo] = None,
        burst_size: Optional[int] = None,
    ) -> None:
        self.server = server
        self.url = url
        self.parsed_url = urllib.parse.urlparse(url)
        if not self.parsed_url.port:
            raise Exception("Missing port for relay %s" % self.parsed_url.geturl())
        self.host_port = self.parsed_url.port
        if not self.parsed_url.hostname:
            raise Exception("Missing hostname for relay %s" % self.parsed_url.geturl())
        self.host_address = self.parsed_url.hostname
        self.path = path
        self.addr_info = addr_info
        self.burst_size = burst_size
        self.on_demand = False
        self.keepalive: Optional[int] = None

    def close(self) -> None:
        self.server.remove_inactivity_timeout(self)
        self.server.loop.unregister(self)
        self.server.check_for_relay_restart(self)
        looping.BaseIOEventHandler.close(self)

    def __str__(self) -> str:
        return "<%s relaying %s for %s>" % (
            self.__class__.__name__,
            self.url,
            self.path,
        )

    def connect(self) -> None:
        return None

    # def handle_event(self, eventmask: int) -> None:
    #     pass


class UDPRelay(Relay):

    # Used to delay starting a source in case we're not getting any
    # data on our UDP socket (dead source, network issue)
    MIN_START_BUFFER = 64 * 2**10

    def __init__(
        self,
        server: "TCPServer",
        url: str,
        path: str,
        addr_info: Optional[AddrInfo] = None,
        burst_size: Optional[int] = None,
    ) -> None:
        super().__init__(server, url, path, addr_info, burst_size)

        # UDP, possibly multicast input
        self.udp_address = (self.host_address, self.host_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(self.udp_address)
        self.sock.setblocking(False)
        if self.parsed_url.scheme == "multicast":
            multicast_request = struct.pack("=4sl", socket.inet_aton(self.host_address), socket.INADDR_ANY)
            self.sock.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, multicast_request)
            # The socket is now multicast ready
        self.initial_buffer_data = b""
        self.server.loop.register(self, looping.POLLIN)
        self.server.update_activity(self)

    def handle_event(self, eventmask: int) -> None:
        if eventmask & looping.POLLIN:
            # FIXME: this is basically a c/c from server.py's
            # HTTPRequest's handle_read
            while True:
                tmp_buffer = helpers.handle_eagain(self.sock.recv, self.MIN_START_BUFFER)
                if tmp_buffer is None:
                    # EAGAIN, we'll come back later
                    break
                else:
                    self.initial_buffer_data = self.initial_buffer_data + tmp_buffer
                if len(self.initial_buffer_data) >= self.MIN_START_BUFFER:
                    # OK, this looks like a valid source (since there
                    # is some socket activity)
                    fake_response_parser = cyhttp11.HTTPClientParser()
                    fake_response_parser.body = self.initial_buffer_data
                    # FIXME: we're assuming an MPEG-TS source
                    fake_response_parser.headers["Content-Type"] = "video/MP2T"
                    self.server.add_source(
                        self.path, self.sock, self.udp_address, fake_response_parser, self.burst_size
                    )
                    break


class HTTPRelay(Relay):

    REQUEST_METHOD = b"GET"
    HTTP_VERSION = b"HTTP/1.0"
    RESPONSE_MAX_SIZE = 4096

    def __init__(
        self,
        server: "TCPServer",
        url: str,
        path: str,
        addr_info: Optional[AddrInfo] = None,
        burst_size: Optional[int] = None,
        on_demand: bool = False,
        keepalive: Optional[int] = None,
    ) -> None:
        super().__init__(server, url, path, addr_info, burst_size)

        self.on_demand = on_demand
        self.od_source: Optional[sources.StreamSource] = None

        # when a source disconnects, its clients can be kept while we try to
        # reconnect to it, this "keepalive" must be an integer in seconds or
        # None, note that it has nothing to do with HTTP keepalive, the name is
        # just here to confuse people
        self.keepalive = keepalive

        self.connect()

    def connect(self) -> None:
        self.create_socket()
        self.register()

    def create_socket(self) -> None:
        addr_info = self.addr_info

        if addr_info:
            self.sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
            self.host_address = addr_info[4][0]
            self.host_port = addr_info[4][1]
        else:
            self.sock = socket.socket()

        self.sock.setblocking(False)
        error = self.sock.connect_ex((self.host_address, self.host_port))
        if error and error != errno.EINPROGRESS:
            raise socket.error(error, errno.errorcode[error])

    def register(self) -> None:
        # self.handle_event = self.handle_connect
        self.server.loop.register(self, looping.POLLOUT)
        self.server.update_activity(self)

    def handle_connect(self, eventmask: int) -> None:
        if eventmask & looping.POLLOUT:
            error = self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if error:
                raise socket.error(error, errno.errorcode[error])
            self.address = self.sock.getpeername()
            # We're connected, prepare to send our request
            _req = self._build_request()
            self.output_buffer = buffer_event.BufferOutputHandler(self.sock, (_req,))
            self.handle_event = self.handle_request  # type: ignore[assignment]
            # Immediately try to send some data
            self.handle_event(eventmask)

    handle_event = handle_connect

    def _build_request(self) -> bytes:
        # FIXME: URL encoding for the request path
        selector = self.parsed_url.path or "/"
        if self.parsed_url.params:
            selector = ";".join([selector, self.parsed_url.params])
        if self.parsed_url.query:
            selector = "?".join([selector, self.parsed_url.query])

        print(type(self.REQUEST_METHOD), type(selector), type(self.HTTP_VERSION))
        request_line = b"%s %s %s" % (self.REQUEST_METHOD, bytes(selector, "ascii"), self.HTTP_VERSION)
        # FIXME: should we send some more headers ?
        headers_lines = helpers.build_http_headers(
            {
                b"Host": bytes(self.host_address, "ascii"),
                b"icy-metadata": b"1",
            },
            b"",
        )
        # FIXME: should we send a body ?
        return b"\r\n".join([request_line, headers_lines, b""])

    def handle_request(self, eventmask: int) -> None:
        if eventmask & looping.POLLOUT:
            self.output_buffer.flush()
            if self.output_buffer.empty():
                # Request sent, switch to HTTP client parsing mode
                self.server.loop.register(self, looping.POLLIN)
                self.response_buffer = b""
                self.response_size = 0
                self.response_parser = cyhttp11.HTTPClientParser()
                self.handle_event = self.handle_response  # type: ignore[assignment]

    def handle_response(self, eventmask: int) -> None:
        if eventmask & looping.POLLIN:
            # FIXME: this is basically a c/c from server.py's
            # HTTPRequest's handle_read
            while True:
                tmp_buffer = helpers.handle_eagain(self.sock.recv, self.RESPONSE_MAX_SIZE - self.response_size)
                if tmp_buffer is None:
                    # EAGAIN, we'll come back later
                    break
                elif tmp_buffer == b"":
                    raise HTTPError("Unexpected end of stream from %s, %s" % (self.url, (self.sock, self.address)))
                self.response_buffer = self.response_buffer + tmp_buffer
                self.response_size += len(tmp_buffer)
                self.response_parser.execute(self.response_buffer)
                if self.response_parser.has_error():
                    raise HTTPParseError("Invalid HTTP response from %s, %s" % (self.sock, self.address))
                elif self.response_parser.is_finished():
                    # Transform this into the appropriate handler
                    self.transform_response()
                    break
                elif self.response_size >= self.RESPONSE_MAX_SIZE:
                    raise HTTPParseError("Oversized HTTP response from %s, %s" % (self.sock, self.address))

    def transform_response(self) -> None:
        if self.response_parser.status_code not in (200,):
            self.server.logger.error(
                "Unexpected response %d %s from %s, %s",
                self.response_parser.status_code,
                self.response_parser.reason_phrase,
                self.url,
                (self.sock, self.address),
            )
            self.close()
            return

        if self.on_demand and self.od_source:
            # give back the control to the source
            self.od_source.on_demand_connected(self.sock, self.response_parser)
            return

        source = sources.find_source(
            self.server,
            self.sock,
            self.address,
            self.response_parser,
            self.path,
            self.burst_size,
            self.on_demand,
            self.keepalive,
        )
        if self.on_demand:
            self.od_source = source
        self.server.register_source(source)

    def close(self) -> None:
        super().close()
        if self.od_source is not None:
            self.od_source.close()
