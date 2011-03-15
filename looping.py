#! -*- coding: utf-8 -*-

import errno
import select
import traceback

POLLIN = select.EPOLLIN
POLLOUT = select.EPOLLOUT
POLLET = select.EPOLLET

class BaseIOEventHandler(object):

    def close(self):
        self.sock.close()
        self.sock = None

    def fileno(self):
        return self.sock.fileno()

class IOLoop(object):

    DEFAULT_TIMEOUT = 0.5

    def __init__(self):
        self.poller = select.epoll()
        self.handlers = {}

    def register(self, io_event_handler, eventmask):
        if io_event_handler.fileno() not in self.handlers:
            self.poller.register(io_event_handler.fileno(), eventmask)
        else:
            self.poller.modify(io_event_handler.fileno(), eventmask)
        self.handlers[io_event_handler.fileno()] = io_event_handler

    def unregister(self, io_event_handler):
        # FIXME: this may need some exception handling
        self.poller.unregister(io_event_handler.fileno())
        del self.handlers[io_event_handler.fileno()]

    def once(self, timeout = 0):
        while True:
            try:
                events_list = self.poller.poll(timeout)
                break
            except IOError, exc:
                if exc.errno == errno.EINTR:
                    continue
                else:
                    raise
        for fd, eventmask in events_list:
            handler = self.handlers[fd]
            try:
                handler.handle_event(eventmask)
            except Exception, exc:
                # We're kinda hardcore
                traceback.print_exc()
                self.unregister(handler)
                handler.close()
