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

        self.output_buffer = buffer_event.BufferOutputHandler(sock)
        self.output_buffer.add_buffer(response.as_bytes())

    def close(self):
        self.server.timeouts.remove_timeout(self)
        self.server.loop.unregister(self)
        BaseIOEventHandler.close(self)

    def flush(self):
        if self.output_buffer.flush():
            self.server.update_activity(self)

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
