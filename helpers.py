# -*- coding: utf-8 -*-

import errno
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
