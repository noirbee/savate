# -*- coding: utf-8 -*-

import errno
import collections
import looping
from looping import BaseIOEventHandler
import buffer_event

def handle_eagain(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except IOError, exc:
        if exc.errno == errno.EAGAIN:
            return None
        else:
            raise

def loop_for_eagain(func, *args, **kwargs):
    try:
        while True:
            func(*args, **kwargs)
    except IOError, exc:
        if exc.errno == errno.EAGAIN:
            pass
        else:
            raise

class HTTPEventHandler(BaseIOEventHandler):

    def __init__(self, server, sock, address, request_parser,
                 status, reason, headers = None, body = b''):
        self.server = server
        self.sock = sock
        self.address = address
        self.request_parser = request_parser

        self.output_buffer = buffer_event.BufferOutputHandler(sock)
        data = self._build_response(status, reason, headers or {}, body)
        self.output_buffer.add_buffer(data)

    def _build_response(self, status, reason, headers, body):
        default_headers = {
            b'Connection': b'close',
            b'Content-Length': len(body),
            }
        default_headers.update(headers)
        status_line = b'HTTP/1.1 %d %s' % (status, reason)
        headers_lines = b''.join(b'%s: %s\r\n' % (key, value) for key, value
                                 in default_headers.items() if value)
        return b'\r\n'.join([status_line, headers_lines, body])

    def finish(self):
        self.output_buffer.flush()
        if self.output_buffer.empty():
            self.server.loop.unregister(self)
            self.close()

    def handle_event(self, eventmask):
        if eventmask & looping.POLLOUT:
            self.finish()

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
        collections.deque.extend(self, iterable)
        self.current_size += sum(len(data) for data in iterable)
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
