import errno
import collections
import signal
import socket
from typing import TYPE_CHECKING, Any, Callable, Iterable, NoReturn, Optional, Protocol, TypeVar, Union

from cyhttp11 import HTTPParser

from savate import looping
from savate.looping import BaseIOEventHandler
from savate import buffer_event
if TYPE_CHECKING:
    from savate.server import TCPServer


AddrInfo = tuple[socket.AddressFamily, socket.SocketKind, int, str, Union[tuple[str, int], tuple[str, int, int, int]]]

_T = TypeVar("_T")

def handle_eagain(func: Callable[..., _T], *args: Any, **kwargs: Any) -> Optional[_T]:
    try:
        return func(*args, **kwargs)
    except IOError as exc:
        if exc.errno == errno.EAGAIN:
            return None
        else:
            raise

def loop_for_eagain(func: Callable[..., _T], *args: Any, **kwargs: Any) -> Optional[_T]:
    try:
        while True:
            return func(*args, **kwargs)
    except IOError as exc:
        if exc.errno == errno.EAGAIN:
            return None
        else:
            raise

def build_http_headers(headers: dict[bytes, Optional[bytes]], body: bytes) -> bytes:
    default_headers: dict[bytes, Optional[bytes]] = {
        b'Connection': b'close',
        b'Content-Length': bytes(str(len(body)), "ascii"),
        }
    default_headers.update(headers)
    return b''.join(b'%s: %s\r\n' % (key, value) for key, value
                    in default_headers.items() if value is not None)


def event_mask_str(event_mask: int) -> str:
    masks_list = ('POLLIN', 'POLLOUT', 'POLLERR', 'POLLHUP')
    return '|'.join(mask for mask in masks_list if
                    event_mask & getattr(looping, mask))


def find_signal_str(signum: int) -> str:
    signal_strings = (sig_str for sig_str in dir(signal) if sig_str.startswith('SIG'))
    for signal_string in signal_strings:
        if getattr(signal, signal_string) == signum:
            return signal_string
    return ''


class HTTPError(Exception):
    pass


class HTTPParseError(HTTPError):
    pass


class HTTPEventHandler(BaseIOEventHandler):

    def __init__(self, server: "TCPServer", sock: socket.socket, address: tuple[str, int], request_parser: HTTPParser, response: "HTTPResponse") -> None:
        self.server = server
        self.sock = sock
        self.address = address
        self.request_parser = request_parser

        self.output_buffer = buffer_event.BufferOutputHandler(sock,
                                                              (response.as_bytes(),))

        # statistics
        self.status = response.status
        self.connect_time = server.loop.now()
        self.bytes_sent = 0

    def close(self) -> None:
        self.server.remove_inactivity_timeout(self)
        self.server.request_out(self.request_parser, self.sock, self.address, self.bytes_sent,
                                self.connect_time, self.status)
        self.server.loop.unregister(self)
        BaseIOEventHandler.close(self)

    def flush(self) -> None:
        try:
            bytes_sent = self.output_buffer.flush()
        except buffer_event.QueueSizeExceeded as exc:
            self.server.logger.info('Client queue size exceeded for %s: %s', self,
                                    exc)
            self.close()
            return None

        if bytes_sent:
            self.server.update_activity(self)
            self.bytes_sent += bytes_sent

    def finish(self) -> None:
        if self.output_buffer.empty():
            self.close()

    def handle_event(self, eventmask: int) -> None:
        if eventmask & looping.POLLOUT:
            try:
                self.flush()
                self.finish()
            except IOError as exc:
                if exc.errno in (errno.EPIPE, errno.ECONNRESET):
                    self.server.logger.error('Connection closed by %s', self)
                    self.close()
                else:
                    raise
        elif eventmask & (looping.POLLERR | looping.POLLHUP):
            # Error / Hangup, client probably closed connection
            self.server.logger.error('Connection closed by %s', self)
            self.close()
        else:
            self.server.logger.error('%s: unexpected eventmask %d (%s)', self, eventmask, event_mask_str(eventmask))

    def __str__(self) -> str:
        return '<%s for %s, %s>' % (
            self.__class__.__name__,
            self.request_parser.request_path,
            self.address,
            )


class HTTPResponse:

    def __init__(self, status: int, reason: bytes, headers: Optional[dict[bytes, Optional[bytes]]] = None, body: bytes = b'') -> None:
        self.status = status
        self.reason = reason
        self.headers = headers or {}
        self.body = body

    def as_bytes(self) -> bytes:
        headers_lines = build_http_headers(self.headers, self.body)
        status_line = b'HTTP/1.0 %d %s' % (self.status, self.reason)
        return b'\r\n'.join([status_line, headers_lines, self.body])


class BurstQueue(collections.deque[bytes]):

    def __init__(self, maxbytes: int, iterable: Iterable[bytes] = ()):
        super().__init__(iterable)
        self.maxbytes = maxbytes
        self.current_size = sum(len(data) for data in iterable)

    def _discard(self) -> None:
        while (self.current_size - len(self[0])) > self.maxbytes:
            self.popleft()

    def append(self, data: bytes) -> None:
        super().append(data)
        self.current_size += len(data)
        self._discard()

    def extend(self, iterable: Iterable[bytes]) -> None:
        for item in iterable:
            super().append(item)
            self.current_size += len(item)
        self._discard()

    def appendleft(self, data: bytes) -> NoReturn:
        raise NotImplementedError('appendleft() makes no sense for this data type')

    def extendleft(self, iterable: Iterable[bytes]) -> NoReturn:
        raise NotImplementedError('extendleft() makes no sense for this data type')

    def remove(self, value: bytes) -> NoReturn:
        raise NotImplementedError('remove() is not supported for this data type')

    def pop(self) -> bytes:  # type: ignore[override]
        ret = super().pop()
        self.current_size -= len(ret)
        return ret

    def popleft(self) -> bytes:
        ret = super().popleft()
        self.current_size -= len(ret)
        return ret

    def clear(self) -> None:
        super().clear()
        self.current_size = 0
