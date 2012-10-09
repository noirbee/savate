# -*- coding: utf-8 -*-

import errno
import collections
import signal

from savate import looping
from savate.looping import BaseIOEventHandler
from savate import buffer_event


def handle_eagain(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except IOError as exc:
        if exc.errno == errno.EAGAIN:
            return None
        else:
            raise

def loop_for_eagain(func, *args, **kwargs):
    try:
        while True:
            func(*args, **kwargs)
    except IOError as exc:
        if exc.errno == errno.EAGAIN:
            pass
        else:
            raise

def build_http_headers(headers, body):
    default_headers = {
        b'Connection': b'close',
        b'Content-Length': len(body),
        }
    default_headers.update(headers)
    return b''.join(b'%s: %s\r\n' % (key, value) for key, value
                    in default_headers.items() if value != None)

def event_mask_str(event_mask):
    masks_list = ('POLLIN', 'POLLOUT', 'POLLERR', 'POLLHUP')
    return '|'.join(mask for mask in masks_list if
                    event_mask & getattr(looping, mask))

def find_signal_str(signum):
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

    def __init__(self, server, sock, address, request_parser, response):
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

    def close(self):
        self.server.remove_inactivity_timeout(self)
        self.server.request_out(self.request_parser, self.sock, self.address, self.bytes_sent,
                                self.connect_time, self.status)
        self.server.loop.unregister(self)
        BaseIOEventHandler.close(self)

    def flush(self):
        bytes_sent = self.output_buffer.flush()
        if bytes_sent:
            self.server.update_activity(self)
            self.bytes_sent += bytes_sent

    def finish(self):
        if self.output_buffer.empty():
            self.close()

    def handle_event(self, eventmask):
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

    def __str__(self):
        return '<%s for %s, %s>' % (
            self.__class__.__name__,
            self.request_parser.request_path,
            self.address,
            )


class HTTPResponse(object):

    def __init__(self, status, reason, headers = None, body = b''):
        self.status = status
        self.reason = reason
        self.headers = headers or {}
        self.body = body

    def as_bytes(self):
        headers_lines = build_http_headers(self.headers, self.body)
        status_line = b'HTTP/1.0 %d %s' % (self.status, self.reason)
        return b'\r\n'.join([status_line, headers_lines, self.body])


class BurstQueue(collections.deque):

    def __init__(self, maxbytes, iterable = ()):
        collections.deque.__init__(self, iterable)
        self.maxbytes = maxbytes
        self.current_size = sum(len(data) for data in iterable)

    def _discard(self):
        while (self.current_size - len(self[0])) > self.maxbytes:
            self.popleft()

    def append(self, data):
        collections.deque.append(self, data)
        self.current_size += len(data)
        self._discard()

    def extend(self, iterable):
        for item in iterable:
            collections.deque.append(self, item)
            self.current_size += len(item)
        self._discard()

    def appendleft(self, data):
        raise NotImplementedError('appendleft() makes no sense for this data type')

    def extendleft(self, iterable):
        raise NotImplementedError('extendleft() makes no sense for this data type')

    def remove(self, value):
        raise NotImplementedError('remove() is not supported for this data type')

    def pop(self):
        ret = collections.deque.pop(self)
        self.current_size -= len(ret)
        return ret

    def popleft(self):
        ret = collections.deque.popleft(self)
        self.current_size -= len(ret)
        return ret

    def clear(self):
        collections.deque.clear(self)
        self.current_size = 0


class Buffer(object):
    """Class that quacks like a :class:`memoryview` (from Python >= 2.7).
    It uses :class:`buffer` builtin which doesn't exist in Python 3.

    """

    __slots__ = (
        'referenced_string',
        'slice',
        'size',
        'encaps_buffer',
    )

    def __init__(self, referenced_string, slice=None, size=None):
        self.referenced_string = referenced_string

        self.slice = 0 if slice is None else slice
        self.size = size

        if slice is None and size is None:
            self.encaps_buffer = buffer(referenced_string)
        elif size is None:
            self.encaps_buffer = buffer(referenced_string, slice)
        elif slice is None:
            self.encaps_buffer = buffer(referenced_string, 0, size)
        else:
            self.encaps_buffer = buffer(referenced_string, slice, size)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.encaps_buffer[key]

        if isinstance(key, tuple) or key.step is not None:
            # only support simple slices without steps
            raise NotImplementedError

        start = key.start if key.start is not None else 0
        new_start = self.slice + start

        if key.stop is None:
            new_size = self.size
        elif self.size is None:
            new_size = key.stop - start
        else:
            old_limit = self.size - (new_start - self.slice)
            new_size = min(
                key.stop - new_start,
                old_limit if old_limit > 0 else 0,
            )
        return Buffer(self.referenced_string, new_start, new_size)

    def __len__(self):
        return len(self.encaps_buffer)

    def __bool__(self):
        return bool(self.encaps_buffer)

    def tobytes(self):
        return str(self.encaps_buffer)


try:
    Buffer = memoryview
except NameError:
    pass
